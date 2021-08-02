# AUTOGENERATED! DO NOT EDIT! File to edit: 00_utils.ipynb (unless otherwise specified).

__all__ = ['clean_img_names', 'check_lists_identical', 'img_path_to_xarr', 'last2dims',
           'check_channels_input_suitable_and_return_channels', 'extend_region_properties_list',
           'add_scale_regionprops_table_area_measurements', 'lazy_props', 'reorder_df_to_put_ch_info_first',
           'region_overlap', 'calculate_overlap', 'generate_touch_counting_image',
           'label_clones_output_unmerged_and_merged', 'get_all_labeled_clones_unmerged_and_merged',
           'determine_labels_across_other_images_using_centroids', 'update_1st_coord_and_dim_of_xarr']

# Cell
import os
import re
from functools import partial, wraps
from glob import glob
from typing import List

import dask.array as da
import dask.dataframe as dd
import numba
import numpy as np
import pandas as pd
import pyclesperanto_prototype as cle
import xarray as xr
from dask import delayed
from dask_image.imread import imread
from matplotlib import pyplot as plt
from scipy.stats import mode
from skimage import measure, segmentation

# Cell
def clean_img_names(img_path_glob: str, img_name_regex: str):
    """clean_img_names takes a "globbed" string pattern, searches
    for all files that match the pattern and extracts image names
    from each file using a regular expression."""
    return [
        re.findall(img_name_regex, os.path.basename(fn))[0]
        for fn in sorted(glob(img_path_glob))
    ]

# Cell
def check_lists_identical(list_of_lists):
    list_a = list_of_lists[0]

    for l in list_of_lists:
        if np.array_equal(l, list_a):
            continue
        else:
            raise ValueError("not all lists have same length!")

# Cell
def img_path_to_xarr(
    img_name_regex: str, pixel_size: float = 0.275, ch_name_for_first_dim:str = 'images', **channel_path_globs
):
    imgs = list()
    channels = list()
    img_names = list()

    for channel_name, img_path_glob in channel_path_globs.items():
        channels.append(channel_name)
        imgs.append(imread(img_path_glob))
        img_names.append(clean_img_names(img_path_glob, img_name_regex))

    check_lists_identical(img_names)
    return xr.DataArray(
        data=da.stack(imgs),
        coords=[
            channels,
            img_names[0],
            np.arange(0, imgs[0].shape[1] * pixel_size, pixel_size),
            np.arange(0, imgs[0].shape[2] * pixel_size, pixel_size),
        ],
        dims=[ch_name_for_first_dim, "img_name", "y", "x"],
    )

# Cell
def last2dims(f):
    def func(array):
        return f(array[0, 0, ...])[None, None, ...]

    return func

# Cell
def check_channels_input_suitable_and_return_channels(
    channels, available_channels: list
):
    if channels is not None:
        try:
            channels + []
            if not set(channels).issubset(available_channels):
                raise ValueError(f"{channels} not in {available_channels}")
        except ValueError:
            raise
        except TypeError:
            raise TypeError("channels must be a list")
        except Exception as e:
            raise
    else:
        channels = available_channels

    return channels

# Cell
def extend_region_properties_list(extra_properties: list = None):
    properties = ["label", "area", "mean_intensity", "centroid"]
    if extra_properties is None:
        pass
    else:
        try:
            properties = properties + extra_properties
        except TypeError:
            raise TypeError("extra_properties must be a list")
        except Exception as e:
            raise e

    return properties

# Cell
def add_scale_regionprops_table_area_measurements(df, pixel_size):
    df_with_um2 = (df.filter(regex=r"area") * (pixel_size ** 2)).add_suffix("_um2")
    return pd.concat([df, df_with_um2], axis=1)

# Cell
@delayed
def lazy_props(seg, img, seg_ch, img_ch, seg_name, img_name, properties, **kwargs):
    df = pd.DataFrame(
        measure.regionprops_table(seg, img, properties=properties, **kwargs)
    )
    df["seg_channel"] = seg_ch
    df["intensity_img_channel"] = img_ch
    df["segmentation_img_name"] = seg_name
    df["intensity_img_name"] = img_name
    return df

# Cell
def reorder_df_to_put_ch_info_first(df):
    first_cols = [
        "seg_channel",
        "intensity_img_channel",
        "segmentation_img_name",
        "intensity_img_name",
    ]
    first_cols.extend(df.columns)
    first_cols = sorted(set(first_cols), key=first_cols.index)
    return df[first_cols]

# Cell
def region_overlap(
    label_no, label_img_outer=None, label_img_inner=None, overlap_thresh=0.5
):
    overlap = label_img_outer[label_img_inner == label_no]
    total_overlap_region = overlap.size
    non_zero_count = np.count_nonzero(overlap)
    ratio_non_zero = non_zero_count / total_overlap_region

    if ratio_non_zero > overlap_thresh:
        is_in = overlap[np.nonzero(overlap)]
        is_in = mode(is_in)[0][0]

    else:
        is_in = 0

    return is_in

# Cell
def calculate_overlap(img, num_of_segs=4, preallocate_value=1000):
    num_dapi = np.unique(img[0])
    l = np.zeros((num_of_segs - 1, preallocate_value), dtype=np.float64)
    l[:] = np.nan
    for label_no in num_dapi:
        for i in range(l.shape[0]):
            l[i, label_no] = region_overlap(label_no, img[i + 1, ...], img[0, ...])
    return l[None, ...]

# Cell
def generate_touch_counting_image(g_img):
    touch_matrix = cle.generate_touch_matrix(cle.push(g_img))
    touch_matrix = cle.set_column(touch_matrix, 0, 0)
    counts = cle.count_touching_neighbors(touch_matrix)
    return cle.replace_intensities(g_img, counts)

# Cell
@delayed
def label_clones_output_unmerged_and_merged(lab_img, to_keep):
    g_lab_img = cle.push(lab_img)

    extended_lab_img = segmentation.clear_border(
        cle.pull(cle.extend_labeling_via_voronoi(g_lab_img))
    )

    filtered_extended_lab = np.isin(extended_lab_img, to_keep) * extended_lab_img
    opposite_filtered_extended_lab = (
        np.invert(np.isin(extended_lab_img, to_keep)) * extended_lab_img
    )

    g_filtered_extended_lab = cle.push(filtered_extended_lab)

    merged_filtered_extended_lab = cle.pull(
        cle.connected_components_labeling_box(
            cle.merge_touching_labels(g_filtered_extended_lab)
        )
    )

    return np.stack(
        [
            lab_img,
            extended_lab_img,
            filtered_extended_lab,
            opposite_filtered_extended_lab,
            merged_filtered_extended_lab,
            cle.pull(generate_touch_counting_image(cle.push(extended_lab_img))),
            cle.pull(generate_touch_counting_image(g_filtered_extended_lab)),
            cle.pull(
                generate_touch_counting_image(cle.push(opposite_filtered_extended_lab))
            ),
        ]
    ).astype(np.uint16)

# Cell
def get_all_labeled_clones_unmerged_and_merged(total_seg_labels, clones_to_keep: dict):
    img_list = list()
    for key in total_seg_labels.coords["img_name"].values:
        img_list.append(
            da.from_delayed(
                label_clones_output_unmerged_and_merged(
                    total_seg_labels.loc[key, ...].data, clones_to_keep[key]
                ),
                shape=(8,) + total_seg_labels.shape[1:],
                dtype=np.uint16,
            )
        )
    return da.stack(img_list, axis=1)

# Cell
@delayed
@numba.njit()
def determine_labels_across_other_images_using_centroids(image_1, centroids, first_output_dim: int = 8, second_output_dim: int = 1000):
    pre_arr = np.zeros((first_output_dim, second_output_dim), dtype=np.float64)
    pre_arr[:] = np.nan
    for i in range(centroids.shape[0]):
        pre_arr[:, i] = image_1[:, centroids[i, 0], centroids[i, 1]]
    return pre_arr

# Cell
def update_1st_coord_and_dim_of_xarr(xarr, new_coord: list, new_dim: str):
    updated_coords = [new_coord] + [coords.data for coords in xarr.coords.values()][1:]
    updated_dims = (new_dim,) + xarr.dims[1:]
    return dict(zip(updated_dims, updated_coords)), updated_dims