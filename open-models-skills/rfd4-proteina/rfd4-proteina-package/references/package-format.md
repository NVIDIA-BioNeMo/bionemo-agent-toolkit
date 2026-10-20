# Package format

## README

State the package name, campaign, criteria-set version, selection rule, number of
annotated inputs and designs, oracle roles/backends present, chain-of-interest
alignment rule, filename convention, and how to interpret missing values.

## Waterfall

For each criterion in its defined order, show label, exact metric name, comparison,
threshold, missing policy, starting count, passed count, failed count, and
cumulative survivors. Provide the overall waterfall followed by one table per
annotated-CIF input.

## Metrics CSV

Write one row per design. Start with `input_cif`, `design_id`, `design_cif`,
`search_config`, and `refolds`, followed by one column per criterion containing the
actual value used in its passer evaluation. Keep on-target and off-target metric
names distinct. Use `NA` only when the criteria policy allows a selected design to
lack a value; explain it in the README.

Do not add per-criterion Boolean columns. The raw values plus the exact waterfall
definition let recipients verify the decision directly.

## Structure names

Input directory names combine a readable input name with its stable input ID.
Design directories use the stable design ID. Refold filenames include the design
ID, normalized oracle role, backend, and prediction ID so multiple on/off-target
predictions remain unambiguous.

The package contains no SQLite database and no links to the original cluster
filesystem.
