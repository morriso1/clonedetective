# AUTOGENERATED! DO NOT EDIT! File to edit: 01_clone_counters.ipynb (unless otherwise specified).

__all__ = ['CloneCounter', 'LazyCloneCounter', 'PersistentCloneCounter']

# Cell
from functools import partial, reduce
from glob import glob
from typing import Callable

import dask.array as da
import dask.dataframe as dd
import numpy as np
import pandas as pd
import xarray as xr
from skimage import measure

from .utils import (
    add_scale_regionprops_table_area_measurements,
    calculate_corresponding_labels,
    calculate_overlap,
    check_channels_input_suitable_and_return_channels,
    determine_labels_across_other_images_using_centroids,
    extend_region_properties_list,
    get_all_labeled_clones_unmerged_and_merged,
    img_path_to_xarr,
    last2dims,
    lazy_props,
    reorder_df_to_put_ch_info_first,
    update_1st_coord_and_dim_of_xarr,
)

# Cell
class CloneCounter:
    def __init__(
        self,
        exp_name: str,
        img_name_regex: str,
        pixel_size: float,
        tot_seg_ch: str = "C0",
    ):
        self.exp_name = exp_name
        self.img_name_regex = img_name_regex
        self.pixel_size = pixel_size
        self.tot_seg_ch = tot_seg_ch

    def add_images(self, **channel_path_globs):
        return img_path_to_xarr(
            self.img_name_regex,
            self.pixel_size,
            ch_name_for_first_dim="img_channels",
            **channel_path_globs,
        )

    def add_segmentations(
        self,
        additional_func_to_map: Callable = None,
        ad_func_kwargs: dict = None,
        **channel_path_globs,
    ):
        segmentations = img_path_to_xarr(
            self.img_name_regex,
            self.pixel_size,
            ch_name_for_first_dim="seg_channels",
            **channel_path_globs,
        )

        if additional_func_to_map is not None:
            segmentations.data = segmentations.data.map_blocks(
                additional_func_to_map, **ad_func_kwargs, dtype=np.uint16
            )

        segmentations.data = segmentations.data.map_blocks(
            last2dims(partial(measure.label)), dtype=np.uint16
        )
        return segmentations

    def combine_C0_overlaps_and_measurements(self):
        ov_df = (
            self.results_overlaps.pivot(
                index=["img_name", "C0_labels"],
                columns=["colocalisation_ch"],
                values="is_in_label",
            )
            .query("C0_labels != 0")
            .copy()
        )
        sk_df = self.results_measurements.query("seg_ch== 'C0'").set_index(
            ["seg_img", "label"]
        )
        sk_df.index.rename(["img_name", "C0_labels"], inplace=True)
        return pd.merge(ov_df, sk_df, left_index=True, right_index=True)

    def determine_seg_img_channel_pairs(
        self, seg_channels: list = None, img_channels: list = None
    ):
        seg_channels = check_channels_input_suitable_and_return_channels(
            channels=seg_channels,
            available_channels=self.image_data.seg_channels.values.tolist(),
        )

        img_channels = check_channels_input_suitable_and_return_channels(
            channels=img_channels,
            available_channels=self.image_data.img_channels.values.tolist(),
        )

        seg_img_channel_pairs = pd.DataFrame()
        seg_img_channel_pairs["image_channel"] = pd.Series(img_channels)
        seg_img_channel_pairs["segmentation_channel"] = pd.Series(seg_channels)
        self.seg_img_channel_pairs = seg_img_channel_pairs.fillna(method="ffill")[
            ["segmentation_channel", "image_channel"]
        ]

    def make_measurements(
        self,
        seg_channels: list = None,
        img_channels: list = None,
        extra_properties: list = None,
        **kwargs,
    ):

        self.determine_seg_img_channel_pairs(seg_channels, img_channels)

        properties = extend_region_properties_list(extra_properties)

        results = list()
        for _, seg_ch, img_ch in self.seg_img_channel_pairs.itertuples():
            for seg, img in zip(
                self.image_data["segmentations"].loc[seg_ch],
                self.image_data["images"].loc[img_ch],
            ):
                results.append(
                    lazy_props(
                        seg.data,
                        img.data,
                        seg.seg_channels.item(),
                        img.img_channels.item(),
                        seg.img_name.item(),
                        img.img_name.item(),
                        properties,
                        **kwargs,
                    )
                )

        df = dd.from_delayed(results).compute()
        df = add_scale_regionprops_table_area_measurements(df, self.pixel_size)
        self.results_measurements = reorder_df_to_put_ch_info_first(df)
        self._determine_max_seg_label_levels()

    def _determine_max_seg_label_levels(self):
        self.tot_seg_ch_max_labels = (
            self.image_data["segmentations"]
            .loc[self.tot_seg_ch]
            .data.map_blocks(
                lambda x: np.unique(x).shape[0], drop_axis=(1, 2), dtype=np.uint16,
            )
            .compute()
            .max()
        )

    def _create_df_from_arr(self, arr):
        return (
            xr.DataArray(
                np.moveaxis(arr, 1, 0),
                coords=(
                    self.image_data["segmentations"].coords["seg_channels"][1:],
                    self.image_data["segmentations"].coords["img_name"],
                    np.arange(self.tot_seg_ch_max_labels),
                ),
                dims=("colocalisation_ch", "img_name", "C0_labels",),
            )
            .to_dataframe("is_in_label")
            .reset_index()
            .dropna()
        )

    def measure_overlap(self):
        self._determine_max_seg_label_levels()
        arr = (
            self.image_data["segmentations"]
            .data.map_blocks(
                calculate_overlap,
                drop_axis=[0],
                dtype=np.float64,
                num_of_segs=self.image_data["segmentations"].shape[0],
                preallocate_value=self.tot_seg_ch_max_labels,
            )
            .compute()
        )

        df = self._create_df_from_arr(arr)
        df["is_in_label"] = df["is_in_label"].astype(np.uint16)
        self.results_overlaps = df[
            ["img_name", "C0_labels", "colocalisation_ch", "is_in_label"]
        ]

    def clones_to_keep_as_dict(self, query_for_pd: str):
        return (
            self.results_measurements.query(query_for_pd)
            .groupby("int_img")
            .agg({"label": lambda x: list(x)})["label"]
            .to_dict()
        )

    def get_centroids_list(self):
        df = self.results_measurements.query("int_img_ch == @self.tot_seg_ch")
        centroids_list = list()
        for img_name in df["int_img"].unique():
            centroids_list.append(
                (
                    df.query("int_img == @img_name")
                    .loc[:, ["centroid-0", "centroid-1"]]
                    .values.astype(int)
                )
            )
        return centroids_list

    def add_clones_and_neighbouring_labels(
        self,
        query_for_pd: str = 'int_img_ch == "C1" & mean_intensity > 1000',
        name_for_query: str = "C1",
        calc_clones: bool = True,
    ):
        new_coord = [
            "extended_tot_seg_labels",
            "total_neighbour_counts",
            f"{name_for_query}pos_neigh_counts",
            f"{name_for_query}neg_neigh_counts",
        ]

        if calc_clones:
            new_coord.append(f"{name_for_query}_clone")

        clone_coords, clone_dims = update_1st_coord_and_dim_of_xarr(
            self.image_data["images"],
            new_coord=new_coord,
            new_dim=f"{name_for_query}_neighbours",
        )

        clones_to_keep = self.clones_to_keep_as_dict(query_for_pd)

        new_label_imgs = get_all_labeled_clones_unmerged_and_merged(
            self.image_data["segmentations"].loc[self.tot_seg_ch],
            clones_to_keep,
            calc_clones,
        )

        return xr.DataArray(
            data=new_label_imgs,
            coords=clone_coords,
            dims=clone_dims,
            attrs={f"{self.tot_seg_ch}_labels_kept_query": query_for_pd},
        )

    def colabels_to_df(self, colabels, name_for_query):
        return (
            xr.DataArray(
                colabels,
                coords=(
                    self.image_data[name_for_query].coords[
                        f"{name_for_query}_neighbours"
                    ],
                    foo.image_data[name_for_query].coords["img_name"],
                    range(1, colabels.shape[2] + 1),
                ),
                dims=(f"{name_for_query}_neighbours", "img_name", "label"),
            )
            .to_dataframe("colabel")
            .reset_index()
            .dropna()
            .pivot(
                index=["img_name", "label"],
                columns=[f"{name_for_query}_neighbours"],
                values="colabel",
            )
            .astype(np.uint16)
            .query("label == extended_tot_seg_labels")
            .eval(f"{name_for_query}pos_neigh_counts = total_neighbour_counts - {name_for_query}neg_neigh_counts")
        )

    def measure_clones_and_neighbouring_labels(self, name_for_query):
        self.get_centroids_list()
        colabels = calculate_corresponding_labels(
            self.image_data[name_for_query].data,
            self.get_centroids_list(),
            self.image_data[name_for_query].shape[0],
            foo.tot_seg_ch_max_labels,
        )

        if not hasattr(self, "results_clones_and_neighbour_counts"):
            self.results_clones_and_neighbour_counts = dict()

        self.results_clones_and_neighbour_counts[name_for_query] = self.colabels_to_df(
            colabels, name_for_query
        )

        self.results_clones_and_neighbour_counts[name_for_query].index.rename(
            ["int_img", "label"], inplace=True
        )

    def combine_neighbour_counts_and_measurements(self):
        list_df = list(self.results_clones_and_neighbour_counts.values()) + [
            self.results_measurements.set_index(["int_img", "label"])
        ]
        merged_df = reduce(
            lambda left, right: pd.merge(
                left,
                right,
                how="left",
                on=["int_img", "label"],
                suffixes=(None, "_extra"),
            ),
            list_df,
        )

        cols_to_drop = merged_df.filter(regex="extra").columns.tolist() + [
            "extended_tot_seg_labels"
        ]

        return merged_df.drop(columns=cols_to_drop)

# Cell
class LazyCloneCounter(CloneCounter):
    def __init__(self, exp_name: str, img_name_regex: str, pixel_size: float):
        super().__init__(exp_name, img_name_regex, pixel_size)

    def add_images(self, **channel_path_globs):
        self.image_data = xr.Dataset(
            {"images": super().add_images(**channel_path_globs)}
        )

    def add_segmentations(
        self,
        additional_func_to_map: Callable = None,
        ad_func_kwargs: dict = None,
        **channel_path_globs
    ):
        self.image_data["segmentations"] = super().add_segmentations(
            additional_func_to_map, ad_func_kwargs, **channel_path_globs
        )

    def add_clones_and_neighbouring_labels(
        self,
        query_for_pd: str = 'int_img_ch == "C1" & mean_intensity > 1000',
        name_for_query: str = "filt_C1_intensity",
        calc_clones: bool = True,
    ):
        self.image_data[name_for_query] = super().add_clones_and_neighbouring_labels(
            query_for_pd, name_for_query, calc_clones
        )

# Cell
class PersistentCloneCounter(CloneCounter):
    def __init__(self, exp_name: str, img_name_regex: str, pixel_size: float):
        super().__init__(exp_name, img_name_regex, pixel_size)

    def add_images(self, **channel_path_globs):
        self.image_data = xr.Dataset(
            {"images": super().add_images(**channel_path_globs)}
        ).persist()

    def add_segmentations(
        self,
        additional_func_to_map: Callable = None,
        ad_func_kwargs: dict = None,
        **channel_path_globs,
    ):
        self.image_data["segmentations"] = (
            super()
            .add_segmentations(
                additional_func_to_map, ad_func_kwargs, **channel_path_globs
            )
            .persist()
        )

    def add_clones_and_neighbouring_labels(
        self,
        query_for_pd: str = 'int_img_ch == "C1" & mean_intensity > 1000',
        name_for_query: str = "filt_C1_intensity",
        calc_clones: bool = True,
    ):
        self.image_data[name_for_query] = (
            super()
            .add_clones_and_neighbouring_labels(
                query_for_pd, name_for_query, calc_clones
            )
            .persist()
        )