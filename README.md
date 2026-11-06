# Monthly updates

Scripts that draw climate maps. Each one fetches the fields it needs, renders the figures in a shared style, and publishes the images. Working files stay in a temporary directory and are removed when the run finishes. Downloads are not stored in git.

The maps share one layout, the same units, and colorblind-safe palettes. Dates on the figures follow AP style. The typeface is Libre Franklin, licensed under the SIL Open Font License (`assets/fonts/OFL.txt`).

## Schedule (UTC)

Runs start shortly after the source data are usually available. Snowfall and the ocean maps run every day, and the snowfall forecast refreshes with each model cycle. The other products run once a month, or once a year.

| Product | When | Why |
| --- | --- | --- |
| Snowfall percentage of average | 15:41 every day | NOAA/NOHRSC season-to-date snowfall for the previous day |
| Predicted snowfall | 00:41, 06:41, 12:41, and 18:41 every day | ECMWF IFS and AIFS snowfall for the next 7 days, from the latest run that reaches 7 days. The 15:41 run refreshes these forecasts too. |
| Weekly precipitation | 00:41, 06:41, 12:41, and 18:41 every day | ECMWF IFS and AIFS total precipitation for the next 7 days, from the latest run that reaches 7 days. |
| Weekly maximum and minimum temperature | 00:41, 06:41, 12:41, and 18:41 every day | ECMWF IFS maximum and minimum 2 m temperature since the previous step, and AIFS 2 m temperature at 6-hour steps, over the next 7 days. Both maps use the same 10°F bins, from −10°F and lower through 110°F and higher. |
| Oceans | 15:41 every day | NASA MUR sea surface temperature and anomaly, and NOAA Coral Reef Watch marine heatwaves. |
| ECMWF seasonal | 12:41 on the 6th | Seasonal fields are typically in by 12:30 |
| ERA5 extremes | 18:41 on the 6th | Monthly means are usually published around the 6th |
| ERA5 precipitable water | 21:41 on the 6th | Same release, started later so the jobs do not overlap |
| ERA5 planetary moisture | 00:41 on the 7th | Same release, started later so the jobs do not overlap |
| Hudson Valley climate | 03:41 on January 7 | The charts cover a full year |
| Moisture trends | 03:41 on January 9 | A full year of ERA5, two days after Hudson Valley |
| NMME | 15:17 on the 8th | The ensemble mean is usually posted later that day |
| C3S multi-model | 12:47 on the 10th | The remaining centres are typically in by 12:30 |
| Climate headlines | 00:47 on the 11th | Twelve hours after the C3S imagery |
