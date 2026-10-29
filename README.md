# Monthly updates

Scripts that draw climate maps. Each one fetches the fields it needs, renders the figures in a shared style, and publishes the images. Working files stay in a temporary directory and are removed when the run finishes. Downloads are not stored in git.

The maps share one layout, the same units, and colorblind-safe palettes. Dates on the figures follow AP style. The typeface is Libre Franklin, licensed under the SIL Open Font License (`assets/fonts/OFL.txt`).

## Schedule (UTC)

Runs start shortly after the source data are usually available.

| Product | When | Why |
| --- | --- | --- |
| ERA5 extremes | 04:11 on the 6th | Monthly means are usually published around the 6th |
| ERA5 precipitable water | 05:11 on the 6th | Same release, started later so the jobs do not overlap |
| Hudson Valley climate | 06:11 on January 6 | The charts cover a full year |
| ECMWF seasonal | 12:41 on the 6th | Seasonal fields are typically in by 12:30 |
| NMME | 15:17 on the 8th | The ensemble mean is usually posted later that day |
| C3S multi-model | 12:47 on the 10th | The remaining centres are typically in by 12:30 |

NMME stops if that month's file is not there yet. It does not reuse an older file.
