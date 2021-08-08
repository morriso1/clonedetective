# AUTOGENERATED! DO NOT EDIT! File to edit: 02_clone_analysis.ipynb (unless otherwise specified).

__all__ = ['combine_agg_functions', 'individual_filter_condition', 'query_df_groupby_by_clone_channel']

# Cell
from functools import reduce

import numpy as np
import pandas as pd

# Cell
def combine_agg_functions(additional_agg_functions):
    if additional_agg_functions is None:
        additional_agg_functions = {}

    agg_functions = {"label": "count", "area_um2": [np.mean, np.std]}
    return {**agg_functions, **additional_agg_functions}

# Cell
def individual_filter_condition(
    df, filtered_col_name: str, query: str, clone_channel: str, agg_functions
):
    temp_df = (
        df.query(query).groupby(["int_img", clone_channel]).agg(agg_functions)
    ).copy()

    temp_df.columns = pd.MultiIndex.from_tuples(
        [(filtered_col_name,) + a for a in temp_df.columns]
    )
    return temp_df

# Cell
def query_df_groupby_by_clone_channel(
    df,
    queries: dict,
    clone_channel: str = "C1",
    additional_agg_functions: dict = None,
):
    """additional agg_functions could be something like:
    additional_agg_functions = {"mean_intensity": [np.mean, np.std]}"""

    agg_functions = combine_agg_functions(additional_agg_functions)
    df = df.reset_index()

    l = list()
    for key, query in queries.items():
        l.append(
            individual_filter_condition(df, key, query, clone_channel, agg_functions)
        )

    return reduce(
        lambda df_left, df_right: pd.merge(
            df_left, df_right, left_index=True, right_index=True
        ),
        l,
    )