# AUTOGENERATED! DO NOT EDIT! File to edit: 01_clone_counters.ipynb (unless otherwise specified).

__all__ = ['CloneCounter', 'LazyCloneCounter', 'PersistentCloneCounter']

# Cell
import re
from functools import partial, reduce
from glob import glob
from typing import Callable

import dask.array as da
import dask.dataframe as dd
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib import pyplot as plt
from skimage import measure

from clonedetective import clone_analysis as ca
from .utils import (
    RGB_image_from_CYX_img,
    add_scale_regionprops_table_area_measurements,
    calc_allfilt_from_thresholds,
    calculate_corresponding_labels,
    calculate_overlap,
    check_channels_input_suitable_and_return_channels,
    concat_list_of_thresholds_to_string,
    extend_region_properties_list,
    four_ch_CYX_img_to_three_ch_CYX_img,
    get_all_labeled_clones_unmerged_and_merged,
    img_path_to_xarr,
    last2dims,
    lazy_props,
    plot_new_images,
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
        self.results_clones_and_neighbour_counts = dict()
        self.defined_thresholds = dict()

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

    def _determine_seg_img_channel_pairs(
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

        self._determine_seg_img_channel_pairs(seg_channels, img_channels)

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

    def testing_possible_thresholds(
        self,
        int_img: str,
        thresholds: list,
        figure_shape=None,
        figure_size=None,
        **kwargs,
    ):
        seg = (
            self.image_data["segmentations"]
            .sel(seg_channels=self.tot_seg_ch, img_name=int_img)
            .compute()
        ).data

        df = self.results_measurements.query("int_img == @int_img")

        thresh_img_dict = dict()
        for thresh in thresholds:
            all_filt = calc_allfilt_from_thresholds(thresh, df)
            to_keep = all_filt[all_filt].reset_index()["label"].values
            thresh = concat_list_of_thresholds_to_string(thresh)
            thresh_img_dict[thresh] = np.isin(seg, to_keep) * seg

        img = (self.image_data["images"].sel(img_name=int_img).compute()).data

        if img.shape[0] == 4:
            img = four_ch_CYX_img_to_three_ch_CYX_img(img)

        imgs_to_plot = [
            RGB_image_from_CYX_img(red=img[2], green=img[1], blue=img[0]),
            seg,
        ] + list(thresh_img_dict.values())

        labels_to_plot = [
            f"composite image",
            f"{self.tot_seg_ch} segmentation",
        ] + list(thresh_img_dict.keys())

        plot_new_images(
            imgs_to_plot,
            labels_to_plot,
            figure_shape=figure_shape,
            figure_size=figure_size,
            **kwargs,
        )

    def _filter_labels(self, thresholds: list, thresh_name: str, calc_clone: bool):
        all_filt = calc_allfilt_from_thresholds(
            thresholds, self.results_measurements.copy()
        )

        if calc_clone:
            all_filt.name = f"{thresh_name}_clonepos"

        else:
            all_filt.name = f"{thresh_name}_pos"

        return (
            all_filt[all_filt == True]
            .reset_index()
            .groupby("int_img")
            .agg({"label": lambda x: list(x)})["label"]
            .to_dict(),
            all_filt,
        )

    def _update_measurements_df_with_all_filt(self, all_filt):
        self.results_measurements = pd.merge(
            self.results_measurements,
            all_filt,
            suffixes=("_unwanted", None),
            on=["int_img", "label"],
        )
        self.results_measurements.drop(
            columns=self.results_measurements.filter(regex="_unwanted").columns,
            inplace=True,
        )

    def add_clones_and_neighbouring_labels(
        self,
        thresholds: list = ['int_img_ch == "C1" & mean_intensity > 1000'],
        thresh_name: str = "C1",
        calc_clones: bool = True,
    ):
        new_coord = [
            "ext_tot_seg_labs",
            f"{thresh_name}_neg_labs",
            f"{thresh_name}_pos_labs",
            "tot_nc",
            f"{thresh_name}neg_nc",
            f"{thresh_name}pos_nc",
        ]

        if calc_clones:
            new_coord.insert(3, f"{thresh_name}_clone")

        clone_coords, clone_dims = update_1st_coord_and_dim_of_xarr(
            self.image_data["images"],
            new_coord=new_coord,
            new_dim=f"{thresh_name}_neighbours",
        )

        labels_to_keep, all_filt = self._filter_labels(
            thresholds, thresh_name, calc_clones
        )

        self._update_measurements_df_with_all_filt(all_filt)

        new_label_imgs = get_all_labeled_clones_unmerged_and_merged(
            self.image_data["segmentations"].loc[self.tot_seg_ch],
            labels_to_keep,
            calc_clones,
        )

        return xr.DataArray(
            data=new_label_imgs,
            coords=clone_coords,
            dims=clone_dims,
            attrs={f"{self.tot_seg_ch}_labels_kept_query": thresholds},
        )

    def _get_centroids_list(self):
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

    def _colabels_to_df(self, colabels, thresh_name):
        return (
            xr.DataArray(
                colabels,
                coords=(
                    self.image_data[thresh_name].coords[f"{thresh_name}_neighbours"],
                    self.image_data[thresh_name].coords["img_name"],
                    range(1, colabels.shape[2] + 1),
                ),
                dims=(f"{thresh_name}_neighbours", "img_name", "label"),
            )
            .to_dataframe("colabel")
            .reset_index()
            .dropna()
            .pivot(
                index=["img_name", "label"],
                columns=[f"{thresh_name}_neighbours"],
                values="colabel",
            )
            .astype(np.uint16)
            .query("label == ext_tot_seg_labs")
        )

    def mutually_exclusive_cell_types(self):
        return (self.results_measurements.filter(regex="_pos").sum(axis=1) <= 1).all()

    def complete_set_of_cell_types(self):
        return (self.results_measurements.filter(regex="_pos").sum(axis=1) > 0).all()

    def measure_clones_and_neighbouring_labels_for_ind_thresh(self, thresh_name):
        colabels = calculate_corresponding_labels(
            self.image_data[thresh_name].data,
            self._get_centroids_list(),
            self.image_data[thresh_name].shape[0],
            self.tot_seg_ch_max_labels,
        )

        df = self._colabels_to_df(colabels, thresh_name)

        df.index.rename(["int_img", "label"], inplace=True)

        self.results_clones_and_neighbour_counts[thresh_name] = df.drop(
            columns=df.filter(regex=r"labs").columns
        )

    def measure_all_clones_and_neighbouring_labels(self):
        if not self.mutually_exclusive_cell_types():
            raise AttributeError('cell types are not mutually exclusive')
        if not self.complete_set_of_cell_types():
            raise AttributeError('cell types are not complete')

        for key in self.defined_thresholds.keys():
            self.measure_clones_and_neighbouring_labels_for_ind_thresh(thresh_name=key)

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

        merged_df = merged_df.drop(
            columns=merged_df.filter(regex="extra").columns
        ).reset_index()

        # fillna in case merge of results_clones_and_neighbour_counts creates NaN
        # when a img_name contains none of a specific cell type
        merged_df[merged_df.filter(regex="clone$|nc").columns] = (
            merged_df.filter(regex="clone$|nc").fillna(0).astype(np.uint16)
        )

        return merged_df

# Cell
class LazyCloneCounter(CloneCounter):
    def __init__(
        self,
        exp_name: str,
        img_name_regex: str,
        pixel_size: float,
        tot_seg_ch: str = "C0",
    ):
        super().__init__(exp_name, img_name_regex, pixel_size)

    def add_images(self, **channel_path_globs):
        self.image_data = xr.Dataset(
            {"images": super().add_images(**channel_path_globs)}
        )

    def add_segmentations(
        self,
        additional_func_to_map: Callable = None,
        ad_func_kwargs: dict = None,
        **channel_path_globs,
    ):
        self.image_data["segmentations"] = super().add_segmentations(
            additional_func_to_map, ad_func_kwargs, **channel_path_globs
        )

    def add_clones_and_neighbouring_labels(
        self,
        thresholds: list = ['int_img_ch == "C1" & mean_intensity > 1000'],
        thresh_name: str = "C1",
        calc_clones: bool = True,
    ):
        self.image_data[thresh_name] = super().add_clones_and_neighbouring_labels(
            thresholds, thresh_name, calc_clones
        )
        self.defined_thresholds[thresh_name] = thresholds

# Cell
class PersistentCloneCounter(CloneCounter):
    def __init__(
        self,
        exp_name: str,
        img_name_regex: str,
        pixel_size: float,
        tot_seg_ch: str = "C0",
    ):
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
        thresholds: list = ['int_img_ch == "C1" & mean_intensity > 1000'],
        thresh_name: str = "C1",
        calc_clones: bool = True,
    ):
        self.image_data[thresh_name] = (
            super()
            .add_clones_and_neighbouring_labels(thresholds, thresh_name, calc_clones)
            .persist()
        )
        self.defined_thresholds[thresh_name] = thresholds