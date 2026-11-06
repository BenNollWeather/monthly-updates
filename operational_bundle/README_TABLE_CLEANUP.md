# Final table cleanup

The C3S table code has been updated for modern pandas:

- `.hide_index()` -> `.hide(axis="index")`
- `.set_precision(2)` -> `.format(precision=2)`
- `DataFrame.append(..., ignore_index=True)` -> `pd.concat([...], ignore_index=True)`
- positional Series access uses `.iloc[...]`
- table captions use current nomenclature and normalized `°C`

No pandas Styler monkeypatch is required in the table scripts.
