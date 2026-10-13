# Banner art sources

The full-size originals. The banner shown in the app is the same name one level up (`../tasks.webp`), made from the
original with `magick`, so a crop or quality change can be redone from here.

| Banner | Made with |
| --- | --- |
| `tasks` | `magick source/tasks.png -gravity South -crop 100%x75%+0+0 +repage -quality 85 tasks.webp` (25% off the top, bottom kept) |
| `attention` | `magick source/attention.png -gravity South -crop 100%x75%+0+0 +repage -quality 85 attention.webp` (same crop as tasks) |
| `upcoming` | `magick source/upcoming.png -flop -gravity South -crop 100%x85%+0+0 +repage -quality 85 upcoming.webp` (mirrored so the robot and the chart sit on the right, which is the part that shows in a narrow card; 15% off the top, bottom kept) |
| `workspace` | `magick source/workspace.png -flop -gravity North -crop 100%x85%+0+0 +repage -quality 85 workspace.webp` (mirrored; 15% off the bottom, top kept) |
