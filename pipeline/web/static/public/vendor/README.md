# Vendored front-end libraries

Third-party JavaScript, committed rather than fetched at runtime.

The public portal is served by the same process as the admin UI, which binds
the LAN and makes no external requests of its own. A CDN `<script>` tag would
mean the portal renders no charts at all without internet access, and would
have every viewer's browser call out to a third party to read a page served
from the machine next to them. These files are here so that the portal works
wherever the pipeline works.

Nothing here is modified. Each file is the published minified build, fetched
from jsDelivr at the exact version pinned below. To upgrade one, replace the
file and update its row — the version in this table is the only record of
what is actually in the tree.

| File | Package | Version | Bytes | Source |
| --- | --- | --- | --- | --- |
| `echarts.min.js` | `echarts` | 5.5.1 | 1,030,855 | https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js |
| `d3.min.js` | `d3` | 7.9.0 | 279,706 | https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js |
| `tabulator.min.js` | `tabulator-tables` | 6.3.0 | 442,539 | https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/js/tabulator.min.js |
| `tabulator_midnight.min.css` | `tabulator-tables` | 6.3.0 | 30,358 | https://cdn.jsdelivr.net/npm/tabulator-tables@6.3.0/dist/css/tabulator_midnight.min.css |
| `fuse.min.js` | `fuse.js` | 7.0.0 | 23,850 | https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js |
| `date-fns.cdn.min.js` | `date-fns` | 3.6.0 | 98,562 | https://cdn.jsdelivr.net/npm/date-fns@3.6.0/cdn.min.js |

Globals exposed: `echarts`, `d3`, `Tabulator`, `Fuse`, `dateFns`.

Licences: ECharts is Apache-2.0; D3, Tabulator, Fuse.js and date-fns are MIT.
Each file carries its own copyright banner, which is why these are the
unmodified minified builds rather than a re-bundle.
