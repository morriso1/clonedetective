# AUTOGENERATED! DO NOT EDIT! File to edit: 00_utils.ipynb (unless otherwise specified).

__all__ = ['clean_img_names', 'check_lists_identical', 'img_path_to_xarr', 'last2dims',
           'check_channels_input_suitable_and_return_channels', 'extend_region_properties_list',
           'add_scale_regionprops_table_area_measurements', 'lazy_props', 'reorder_df_to_put_ch_info_first',
           'is_label_image', 'generate_random_cmap', 'what_cmap', 'figure_rows_columns', 'auto_figure_size',
           'crop_RGB_img_to_square', 'plot_new_images', 'RGB_image_from_CYX_img', 'four_ch_CYX_img_to_three_ch_CYX_img',
           'region_overlap', 'calculate_overlap', 'calc_allfilt_from_thresholds', 'concat_list_of_thresholds_to_string',
           'generate_touch_counting_image', 'adjusted_cell_touch_images', 'calc_neighbours',
           'get_all_labeled_clones_unmerged_and_merged', 'determine_labels_across_other_images_using_centroids',
           'calculate_corresponding_labels', 'update_1st_coord_and_dim_of_xarr']

# Cell
import os
import re
import string
from glob import glob
from itertools import zip_longest
from typing import Callable, List, Tuple

import dask.array as da
import dask.dataframe as dd
import matplotlib
import numba
import numpy as np
import pandas as pd
import pyclesperanto_prototype as cle
import xarray as xr
from dask import delayed
from dask_image.imread import imread
from matplotlib import pyplot as plt
from scipy.stats import mode
from skimage import exposure, img_as_ubyte, measure, segmentation

# Cell
def clean_img_names(img_path_glob: str, img_name_regex: str) -> list:
    """clean_img_names takes a "globbed" string pattern, searches for all files that match the pattern and extracts image names from each file using a regular expression.

    Args:
        img_path_glob (str): A globbed string pattern e.g. "C1/*.tif"
        img_name_regex (str): A regex pattern used to parse out image names from filenames e.g. r"\w\d\w\d\d\p\d"

    Returns:
        list: Parsed image filenames stored in a list.
    """
    return [
        re.findall(img_name_regex, os.path.basename(fn))[0]
        for fn in sorted(glob(img_path_glob))
    ]

# Cell
def check_lists_identical(list_of_lists: List[List]):
    """Checks if all lists within a list are identical. Raises a ValueError exception if not.

    Args:
        list_of_lists (list[list]): List of lists. Can contain anything e.g. strings, numbers.

    Raises:
        ValueError: Exception.
    """
    list_a = list_of_lists[0]

    for l in list_of_lists:
        if np.array_equal(l, list_a):
            continue
        else:
            raise ValueError("not all sublists are identical!")

# Cell
def img_path_to_xarr(
    img_name_regex: str,
    pixel_size: float = 0.275,
    ch_name_for_first_dim: str = "images",
    **channel_path_globs,
):
    """Takes channel path globs and creates a dask backed xarray dataarray"

    Args:
        img_name_regex (str): A regex pattern used to parse out image names from filenames e.g. r"\w\d\w\d\d\p\d"
        pixel_size (float, optional): Defaults to 0.275.
        ch_name_for_first_dim (str, optional): Defaults to "images".
        **channel_path_globs: required e.g. C0="data/MARCM_experiment/images/C0/*.tif"

    Returns:
        xarray dataarray: dask backed xarray dataarray of images
    """
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
def last2dims(f: Callable):
    """Decorator function for operating on the last two dimensions of an array. Useful with dask map blocks.

    Args:
        f (Callable): Function
    """

    def func(array):
        return f(array[0, 0, ...])[None, None, ...]

    return func

# Cell
def check_channels_input_suitable_and_return_channels(
    channels: List, available_channels: List
) -> List:
    """Checks if inputted channels are within a available channels list. If so, return inputted channels. If no channels given, returns all available channels.

    Args:
        channels (List): List of desired channels.
        available_channels (List): List of available channels.

    Raises:
        ValueError: channels are not in available channels.
        TypeError: channels and availables channels must be of type list

    Returns:
        List: channels to be used.
    """
    if channels is not None:
        try:
            channels + []
            available_channels + []
            if not set(channels).issubset(available_channels):
                raise ValueError(f"{channels} not in {available_channels}")
        except ValueError:
            raise
        except TypeError:
            raise TypeError("channels and available channels must be lists")
        except Exception as e:
            raise
    else:
        channels = available_channels

    return channels

# Cell
def extend_region_properties_list(extra_properties: List = None) -> List:
    """Adds more properties to scikit-image regionprops function. Defaults are ["label", "area", "mean_intensity", "centroid"].

    Args:
        extra_properties (List, optional): See scikit-image regionprops for possible extra properties. Defaults to None.

    Raises:
        TypeError: extra_properties must be a list.
        e: remaining exceptions.

    Returns:
        List: extra properties appended to default properties.
    """
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
def add_scale_regionprops_table_area_measurements(
    df: pd.DataFrame, pixel_size: int
) -> pd.DataFrame:
    """Extra column(s) in regionprops for areas in um2.

    Args:
        df (pd.DataFrame): Dataframe generated by scikit-image regionprops_table
        pixel_size (int): pixel size in um2.

    Returns:
        pd.DataFrame: Regionprops dataframe with extra area in um2 columns.
    """
    df_with_um2 = (df.filter(regex=r"area") * (pixel_size ** 2)).add_suffix("_um2")
    return pd.concat([df, df_with_um2], axis=1)

# Cell
@delayed(name="lazy_props")
def lazy_props(seg, img, seg_ch, img_ch, seg_name, img_name, properties, **kwargs):
    df = pd.DataFrame(
        measure.regionprops_table(seg, img, properties=properties, **kwargs)
    )
    df["seg_ch"] = seg_ch
    df["int_img_ch"] = img_ch
    df["seg_img"] = seg_name
    df["int_img"] = img_name
    return df

# Cell
def reorder_df_to_put_ch_info_first(df: pd.DataFrame) -> pd.DataFrame:
    """reorders a pandas dataframe to channel columns first e.g. "int_img_ch"

    Args:
        df (pd.DataFrame): pandas dataframe containing channel columns.

    Returns:
        pd.DataFrame: pandas dataframe with the channel columns first
    """
    first_cols = [
        "seg_ch",
        "int_img_ch",
        "seg_img",
        "int_img",
    ]
    first_cols.extend(df.columns)
    first_cols = sorted(set(first_cols), key=first_cols.index)
    return df[first_cols]

# Cell
def is_label_image(img: np.array, unique_value_thresh: int = 2000) -> bool:
    """Tests whether supplied image is a label image based on the number of unique values in the image.

    Args:
        img (np.array): image
        unique_value_thresh (int, optional): Defaults to 2000.

    Returns:
        bool: is the supplied image a label image.
    """
    return np.unique(img).shape[0] < 2000

# Cell
def generate_random_cmap(num_of_colors: int = 2000) -> matplotlib.colors.ListedColormap:
    """Uses matplotlib to generate a random cmap.

    Args:
        num_of_colors (int, optional): Defaults to 2000.

    Returns:
        matplotlib.colors.ListedColormap: colormap that can be use when plotting e.g. cmap=custom_cmap
    """
    colors = np.random.rand(num_of_colors, 3)
    colors[0, :] = 0
    return matplotlib.colors.ListedColormap(colors)

# Cell
def what_cmap(
    img: np.array,
    img_cmap: matplotlib.colors.ListedColormap,
    label_cmap: matplotlib.colors.ListedColormap,
) -> matplotlib.colors.ListedColormap:
    """Determines whether to use a image cmap (e.g. gray) or a label cmap (e.g. random)

    Args:
        img (np.array)
        img_cmap (matplotlib.colors.ListedColormap)
        label_cmap (matplotlib.colors.ListedColormap)

    Returns:
        matplotlib.colors.ListedColormap: image cmap (e.g. gray) or a label cmap (e.g. random).
    """
    return label_cmap if is_label_image(img) else img_cmap

# Cell
def figure_rows_columns(total_fig_axes: int, rows: int = 3) -> Tuple:
    """Calculates the sensible default number of columns and rows for a figure.

    Args:
        total_fig_axes (int): Total number figure axes e.g. for 3x3 grid, would be 9.
        rows (int, optional): How many rows. Defaults to 3.

    Returns:
        Tuple: Number of columns and rows for a figure
    """
    return (np.ceil(total_fig_axes / rows).astype(int), rows)

# Cell
def auto_figure_size(figure_shape: Tuple, scaling_factor: int = 4) -> Tuple:
    """Scales figure shape to generate figure dimensions.

    Args:
        figure_shape (Tuple): Figure shape in determines of rows and columns.
        scaling_factor (int, optional): Defaults to 4.

    Returns:
        Tuple: figure dimensions in inches for matplotlib.
    """
    return figure_shape[1] * scaling_factor, figure_shape[0] * scaling_factor

# Cell
def crop_RGB_img_to_square(RGB_img: np.array) -> np.array:
    """Crops an RGB image to a square e.g useful after taking a napari screenshot.

    Args:
        RGB_img (np.array): Image of form (y,x,c).

    Returns:
        np.array: cropped image
    """
    y, x = RGB_img.shape[:2]
    if y > x:
        y_min = (y - x) // 2
        y_max = y - y_min
        return RGB_img[y_min:y_max, :]
    elif x > y:
        x_min = (x - y) // 2
        x_max = x - x_min
        return RGB_img[:, x_min:x_max]
    else:
        print("already a square!")
        return RGB_img

# Cell
def plot_new_images(
    images: List[np.array],
    label_text: List[str],
    label_letter: str = None,
    figure_shape: tuple = None,
    figure_size: tuple = None,
    img_cmap: str = "gray",
    label_cmap: str = None,
    colorbar: bool = False,
    colorbar_title: str = "number of neighbours",
    **kwargs,
):
    """Plots a grid of images with labels.

    Args:
        images (list[np.array]): List of numpy arrays. Can be RGB or 2D.
        label_text (list[str]): List of image labels.
        label_letter (str, optional): e.g. ABCDE Defaults to None.
        figure_shape (tuple, optional): e.g. four rows and columns (4,4) Defaults to None.
        figure_size (tuple, optional): e.g. a 12 by 12 image (12, 12) Defaults to None.
        img_cmap (str, optional): Defaults to "gray".
        label_cmap (str, optional): Defaults to None.
        colorbar (bool, optional): Defaults to False.
        colorbar_title (str, optional): Defaults to "number of neighbours".
    """
    if figure_shape is None:
        figure_shape = figure_rows_columns(len(images))

    if figure_size is None:
        figure_size = auto_figure_size(figure_shape)

    fig, ax = plt.subplots(
        nrows=figure_shape[0], ncols=figure_shape[1], figsize=figure_size,
    )

    if label_cmap is None:
        label_cmap = generate_random_cmap()

    if label_letter is None:
        label_letter = string.ascii_lowercase[: len(label_text)]

    for (img, ax, letter, text) in zip_longest(
        images, ax.flatten(), label_letter, label_text
    ):
        if img is not None:
            im = ax.imshow(img, cmap=what_cmap(img, img_cmap, label_cmap), **kwargs)
            ax.set_title(f"({letter}) {text}")
            ax.axis("off")
        else:
            ax.set_axis_off()
    if colorbar:
        fig2, cax = plt.subplots(figsize=(figure_shape[1], 1))
        plt.colorbar(im, cax=cax, orientation="horizontal")
        cax.set_title(colorbar_title)
        fig.axes.append(cax)

    plt.tight_layout()

# Cell
def RGB_image_from_CYX_img(
    red: np.array = None,
    green: np.array = None,
    blue: np.array = None,
    ref_ch: int = 2,
    clims: Tuple = (2, 98),
) -> np.array:
    """Takes individual, equal-sized 2D numby arrays and generates an RGB image of the form (Y,X,C).

    Args:
        red (np.array, optional): Defaults to None.
        green (np.array, optional): Defaults to None.
        blue (np.array, optional): Defaults to None.
        ref_ch (int, optional): Channel used to define shape. Defaults to 2.
        clims (Tuple, optional): Adjust contrast limits. Defaults to (2, 98).

    Returns:
        np.array: [description]
    """
    RGB_image = list([red, green, blue])
    for i in range(len(RGB_image)):
        if RGB_image[i] is None:
            RGB_image[i] = np.zeros(RGB_image[ref_ch].shape, dtype=np.uint8)
        else:
            RGB_image[i] = img_as_ubyte(RGB_image[i].copy())
            RGB_image[i] = exposure.rescale_intensity(
                RGB_image[i],
                in_range=(
                    np.percentile(RGB_image[i], clims[0]),
                    np.percentile(RGB_image[i], clims[1]),
                ),
            )

    return np.stack(RGB_image, axis=2)

# Cell
def four_ch_CYX_img_to_three_ch_CYX_img(img: np.array) -> np.array:
    """Converts a four channel CYX image into a three channel CYX image.

    Args:
        img (np.array): Four channel CYX image.

    Returns:
        np.array: Three channel CYX image.
    """
    img[0] = img[0] + img[3]
    img[1] = img[1] + img[3]
    img[2] = img[2] + img[3]
    return img

# Cell
def region_overlap(
    label_no: int,
    label_img_outer: np.array,
    label_img_inner: np.array,
    overlap_thresh: int = 0.5,
) -> int:
    """Determine which two regions overlap in two label images.

    Args:
        label_no (int): Label number in the inner label image to look for overlap with.
        label_img_outer (np.array): Outer label image i.e. the one for which we are testing overlap against.
        label_img_inner (np.array): Inner label image i.e. the image contain the label_no provide in the first argument.
        overlap_thresh (int, optional): How much overlap between two labels to call an overlap. Defaults to 0.5.

    Returns:
        int: Label in outer label image which overlaps with label_no.
    """
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
def calculate_overlap(
    img: np.array, num_of_segs: int = 4, preallocate_value: int = 1000,
) -> np.array:
    """Calculates overlap between stack of label images.

    Args:
        img (np.array): Label image with channel first.
        num_of_segs (int, optional): Defaults to 4.
        preallocate_value (int, optional): Defaults to 1000.

    Returns:
        np.array: Array of overlaps
    """
    num_dapi = np.unique(img[0])
    l = np.zeros((num_of_segs - 1, preallocate_value), dtype=np.float64)
    l[:] = np.nan
    for label_no in num_dapi:
        for i in range(l.shape[0]):
            l[i, label_no] = region_overlap(label_no, img[i + 1, ...], img[0, ...])
    return l[None, ...]

# Cell
def calc_allfilt_from_thresholds(thresholds: list, df):
    filt_l = list()

    # loop through and accumulate filter masks
    for thresh in thresholds:
        filt_l.append(df.eval(thresh))

    # combine filter masks together
    return (
        pd.DataFrame(
            np.stack(filt_l, axis=1),
            index=pd.MultiIndex.from_frame(df[["int_img", "label"]]),
        )
        .groupby(["int_img", "label"])
        .any()
        .all(axis=1)
    )

# Cell
def concat_list_of_thresholds_to_string(thresholds):
    thresholds = "\n\n".join(thresholds)
    return re.sub(r"&", r"&\n", thresholds)

# Cell
def generate_touch_counting_image(g_img):
    touch_matrix = cle.generate_touch_matrix(cle.push(g_img))
    touch_matrix = cle.set_column(touch_matrix, 0, 0)
    counts = cle.count_touching_neighbors(touch_matrix)
    return cle.replace_intensities(g_img, counts)

# Cell
def adjusted_cell_touch_images(
    total_neigh_counts, neg_neigh_neg, pos_neigh_pos, pos_binary_image
):
    neg_neigh_pos = (
        total_neigh_counts - neg_neigh_neg - pos_neigh_pos
    ) * pos_binary_image

    pos_neigh_neg = (total_neigh_counts - neg_neigh_neg - pos_neigh_pos) * np.invert(
        pos_binary_image
    )

    neg_neigh_counts = neg_neigh_neg + neg_neigh_pos

    pos_neigh_counts = pos_neigh_pos + pos_neigh_neg

    return neg_neigh_counts, pos_neigh_counts

# Cell
@delayed(name="calc_neighbours")
def calc_neighbours(lab_img, to_keep, calc_clones):
    g_lab_img = cle.push(lab_img)

    extended_lab_img = segmentation.clear_border(
        cle.pull(cle.extend_labeling_via_voronoi(g_lab_img))
    )

    binary_filt = np.isin(extended_lab_img, to_keep)
    filtered_extended_lab = binary_filt * extended_lab_img
    opposite_filtered_extended_lab = np.invert(binary_filt) * extended_lab_img

    g_filtered_extended_lab = cle.push(filtered_extended_lab)

    total_neigh_counts = cle.pull(
        generate_touch_counting_image(cle.push(extended_lab_img))
    )
    pos_neigh_pos = cle.pull(
        generate_touch_counting_image(cle.push(filtered_extended_lab))
    )
    neg_neigh_neg = cle.pull(
        generate_touch_counting_image(cle.push(opposite_filtered_extended_lab))
    )

    neg_neigh_counts, pos_neigh_counts = adjusted_cell_touch_images(
        total_neigh_counts, neg_neigh_neg, pos_neigh_pos, binary_filt
    )

    stack = [
        extended_lab_img,
        opposite_filtered_extended_lab,
        filtered_extended_lab,
        total_neigh_counts,
        neg_neigh_counts,
        pos_neigh_counts,
    ]

    if calc_clones:
        stack.insert(
            3,
            cle.pull(
                cle.connected_components_labeling_box(
                    cle.merge_touching_labels(g_filtered_extended_lab)
                )
            ),
        )

    return np.stack(stack).astype(np.uint16)

# Cell
def get_all_labeled_clones_unmerged_and_merged(
    total_seg_labels, labels_to_keep: dict, calc_clones: bool
):
    img_list = list()
    first_dim = 6 + int(calc_clones)
    for key in total_seg_labels.coords["img_name"].values:
        try:
            img_list.append(
                da.from_delayed(
                    calc_neighbours(
                        total_seg_labels.loc[key, ...].data,
                        labels_to_keep[key],
                        calc_clones,
                    ),
                    shape=(first_dim,) + total_seg_labels.shape[1:],
                    dtype=np.uint16,
                )
            )
        # KeyError exception occurs when query did not yield any labels to keep.
        # Therefore, append empty array for this key instead.
        except KeyError:
            img_list.append(
                da.zeros(
                    shape=(first_dim,) + total_seg_labels.shape[1:], dtype=np.uint16
                )
            )
    return da.stack(img_list, axis=1)

# Cell
@delayed(name="determine_labels_across_other_images_using_centroids")
@numba.njit()
def determine_labels_across_other_images_using_centroids(
    image_1, centroids, first_output_dim, second_output_dim
):
    pre_arr = np.zeros((first_output_dim, second_output_dim), dtype=np.float64)
    pre_arr[:] = np.nan
    for i in range(centroids.shape[0]):
        pre_arr[:, i] = image_1[:, centroids[i, 0], centroids[i, 1]]
    return pre_arr

# Cell
def calculate_corresponding_labels(
    labels, centroids_list, first_output_dim, second_output_dim
):
    if not labels.shape[1] == len(centroids_list):
        raise ValueError("not the same numbers of imgs as centroid pairs!")

    img_list = list()
    for i in range(labels.shape[1]):
        img_list.append(
            da.from_delayed(
                determine_labels_across_other_images_using_centroids(
                    labels[:, i], centroids_list[i], first_output_dim, second_output_dim
                ),
                shape=(first_output_dim, second_output_dim),
                dtype=np.float64,
            )
        )
    return da.stack(img_list, axis=1)

# Cell
def update_1st_coord_and_dim_of_xarr(xarr, new_coord: list, new_dim: str):
    updated_coords = [new_coord] + [coords.data for coords in xarr.coords.values()][1:]
    updated_dims = (new_dim,) + xarr.dims[1:]
    return dict(zip(updated_dims, updated_coords)), updated_dims