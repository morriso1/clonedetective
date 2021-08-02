# AUTOGENERATED! DO NOT EDIT! File to edit: 01_clone_counters.ipynb (unless otherwise specified).

__all__ = ['CloneCounter', 'LazyCloneCounter', 'PersistentCloneCounter']

# Cell
from functools import partial
from glob import glob

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
    def __init__(self, exp_name: str, img_name_regex: str, pixel_size: float):
        self.exp_name, self.img_name_regex, self.pixel_size = (
            exp_name,
            img_name_regex,
            pixel_size,
        )

    def add_images(self, **channel_path_globs):
        return img_path_to_xarr(
            self.img_name_regex,
            self.pixel_size,
            ch_name_for_first_dim="img_channels",
            **channel_path_globs,
        )

    def add_segmentations(self, **channel_path_globs):
        segmentations = img_path_to_xarr(
            self.img_name_regex,
            self.pixel_size,
            ch_name_for_first_dim="seg_channels",
            **channel_path_globs,
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
        sk_df = self.results_measurements.query("seg_channel == 'C0'").set_index(
            ["segmentation_img_name", "label"]
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

    def _determine_max_seg_label_levels(self, seg_channel):
        """Determines in self.max_seg_label_levels is unassigned and create empty.
        Then adds `seg_channel` as new key and corresponding max segmentation label levels
        as value"""

        try:
            self.max_seg_label_levels.setdefault(seg_channel, []).append(
                (
                    self.image_data["segmentations"]
                    .loc[seg_channel]
                    .data.map_blocks(
                        lambda x: np.unique(x).shape[0],
                        drop_axis=(1, 2),
                        dtype=np.uint16,
                    )
                    .compute()
                    .max()
                )
            )
            self.max_seg_label_levels[seg_channel] = self.max_seg_label_levels[
                seg_channel
            ][0]
        except AttributeError:
            self.max_seg_label_levels = dict()
            self._determine_max_seg_label_levels(seg_channel)

    def _create_df_from_arr(self, arr):
        return (
            xr.DataArray(
                np.moveaxis(arr, 1, 0),
                coords=(
                    self.image_data["segmentations"].coords["seg_channels"][1:],
                    self.image_data["segmentations"].coords["img_name"],
                    np.arange(self.max_seg_label_levels["C0"]),
                ),
                dims=("colocalisation_ch", "img_name", "C0_labels",),
            )
            .to_dataframe("is_in_label")
            .reset_index()
            .dropna()
        )

    def measure_overlap(self):
        self._determine_max_seg_label_levels("C0")
        arr = (
            self.image_data["segmentations"]
            .data.map_blocks(
                calculate_overlap,
                drop_axis=[0],
                dtype=np.float64,
                num_of_segs=self.image_data["segmentations"].shape[0],
                preallocate_value=self.max_seg_label_levels["C0"],
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
            .groupby("intensity_img_name")
            .agg({"label": lambda x: list(x)})["label"]
            .to_dict()
        )

    def get_centroids_list(self, tot_seg_ch: str = "C0"):
        df = self.results_measurements.query("intensity_img_channel == @tot_seg_ch")
        centroids_list = list()
        for img_name in df["intensity_img_name"].unique():
            centroids_list.append(
                (
                    df.query("intensity_img_name == @img_name")
                    .loc[:, ["centroid-0", "centroid-1"]]
                    .values.astype(int)
                )
            )
        return centroids_list

    def add_clones_and_neighbouring_labels(
        self,
        tot_seg_ch: str = "C0",
        query_for_pd: str = 'intensity_img_channel == "C1" & mean_intensity > 1000',
        name_for_query: str = "filt_C1_intensity",
    ):
        clone_coords, clone_dims = update_1st_coord_and_dim_of_xarr(
            self.image_data["images"],
            new_coord=[
                f"{tot_seg_ch}",
                f"{tot_seg_ch}_extended",
                f"{tot_seg_ch}_inside_clones",
                f"{tot_seg_ch}_outside_clones",
                f"merged_clones",
                f"{tot_seg_ch}_neighbour_counts",
                f"{tot_seg_ch}_inside_clones_neighbour_counts",
                f"{tot_seg_ch}_outside_clones_neighbour_counts",
            ],
            new_dim="extended_labels_neighbour_counts",
        )

        clones_to_keep = self.clones_to_keep_as_dict(query_for_pd)

        new_label_imgs = get_all_labeled_clones_unmerged_and_merged(
            self.image_data["segmentations"].loc[tot_seg_ch], clones_to_keep
        )

        self.image_data[f"{name_for_query}_clones_and_neighbour_counts"] = xr.DataArray(
            data=new_label_imgs,
            coords=clone_coords,
            dims=clone_dims,
            attrs={f"{tot_seg_ch}_labels_kept_query": query_for_pd},
        )

# Cell
class LazyCloneCounter(CloneCounter):
    def __init__(self, exp_name: str, img_name_regex: str, pixel_size: float):
        super().__init__(exp_name, img_name_regex, pixel_size)

    def add_images(self, **channel_path_globs):
        self.image_data = xr.Dataset(
            {"images": super().add_images(**channel_path_globs)}
        )

    def add_segmentations(self, **channel_path_globs):
        self.image_data["segmentations"] = super().add_segmentations(
            **channel_path_globs
        )

# Cell
class PersistentCloneCounter(CloneCounter):
    def __init__(self, exp_name: str, img_name_regex: str, pixel_size: float):
        super().__init__(exp_name, img_name_regex, pixel_size)

    def add_images(self, **channel_path_globs):
        self.image_data = xr.Dataset(
            {"images": super().add_images(**channel_path_globs)}
        ).persist()

    def add_segmentations(self, **channel_path_globs):
        self.image_data["segmentations"] = (
            super().add_segmentations(**channel_path_globs).persist()
        )