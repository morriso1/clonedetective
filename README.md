# py_clone_detective
> A python library for automated cell lineage analysis.


<img src="docs/images/py_clone_detector_scheme.png">

## Install

pip install not yet supported but will be soon!

`pip install coming_soon`

## How to use - simple use case

For a more detailed walkthrough, please see individual tutorials.

#### Import and instantiate CloneCounter subclass:

The LazyCloneCounter subclass uses Dask to lazy load image series that maybe too large to fit in RAM.

```
from py_clone_detective.clone_counters import LazyCloneCounter
```

We intialise a LazyCloneCounter with four required arguments:
1) **exp_name** : str -> name of the experiment
2) **img_name_regex** : str -> regular expression used to extract unique identifies from image filenames
3) **pixel_size** : str -> pixel size in $\mu m^{2}$
4) **tot_seg_ch** : str -> image channel used to define the total number of cells e.g. DAPI channel.

```
exp = LazyCloneCounter()
```

#### Read images
