# Monthly updates

Scripts that draw the climate maps and forecast pages. A run fetches what it needs, draws it in the shared style, and publishes the result. Dates follow AP style. The typeface is Libre Franklin, under the SIL Open Font License (`assets/fonts/OFL.txt`). Downloads are not stored in git.

## Schedule (UTC)

Forecast jobs use the latest ECMWF run that reaches 7 days. IFS is the 0.1° grid and is published about two hours after the 0.25° dissemination, so the 00 UTC run is refreshed at 10:41 and the 12 UTC run at 22:41. AIFS stays at 0.25° and is also refreshed at 02:41 and 14:41, after the 18 and 06 UTC runs. The NOAA snowfall file is the previous day's 12 UTC analysis and is usually posted before 10:41. Ocean heatwaves update in the afternoon, US Eastern time. The monthly and yearly jobs start after their source data are usually out.

| Product | When | Detail |
| --- | --- | --- |
| Snowfall percentage of average | 10:41 every day | NOAA/NOHRSC season-to-date snowfall for the previous day. Later forecast runs refresh it when that file is late. |
| Predicted snowfall | 02:41, 10:41, 14:41, and 22:41 every day | IFS and AIFS snowfall for the next 7 days |
| Weekly precipitation | 02:41, 10:41, 14:41, and 22:41 every day | IFS and AIFS total precipitation for the next 7 days |
| Weekly maximum and minimum temperature | 02:41, 10:41, 14:41, and 22:41 every day | IFS maximum and minimum since the previous step, and AIFS temperature every 6 hours. Both maps use 10°F bins, from −10°F and lower through 110°F and higher. |
| Oceans | 20:41 every day | NASA MUR sea-surface temperature and anomaly, and NOAA Coral Reef Watch marine heatwaves |
| ECMWF seasonal | 12:41 on the 6th | Seasonal fields are typically in by 12:30 |
| ERA5 extremes | 18:41 on the 6th | Monthly means are usually published around the 6th |
| ERA5 precipitable water | 21:41 on the 6th | Same release, after extremes |
| ERA5 planetary moisture | 00:41 on the 7th | Same release, after precipitable water |
| Hudson Valley climate | 03:41 on January 7 | A full year of ERA5 |
| Moisture trends | 03:41 on January 9 | A full year of ERA5 |
| NMME | 15:17 on the 8th | The ensemble mean is usually posted that day |
| C3S multi-model | 12:47 on the 10th | The remaining centres are typically in by 12:30 |
| Climate headlines | 00:47 on the 11th | Twelve hours after the C3S imagery |
