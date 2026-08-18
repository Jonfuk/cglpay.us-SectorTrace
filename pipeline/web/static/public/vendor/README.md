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
| `leaflet.js` | `leaflet` | 1.9.4 | 147,552 | https://unpkg.com/leaflet@1.9.4/dist/leaflet.js |
| `leaflet.css` | `leaflet` | 1.9.4 | 14,806 | https://unpkg.com/leaflet@1.9.4/dist/leaflet.css |
| `fuse.min.js` | `fuse.js` | 7.0.0 | 23,850 | https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js |
| `bootstrap.min.css` | `bootstrap` | 5.3.8 | 232,111 | https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css |
| `bootstrap.bundle.min.js` | `bootstrap` | 5.3.8 | 80,496 | https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js |

Globals exposed: `echarts`, `d3`, `Tabulator`, `L`, `Fuse`, and Bootstrap's `bootstrap` namespace.

Licences: Bootstrap is MIT; ECharts is Apache-2.0; D3, Tabulator, Leaflet and Fuse.js are MIT.
Each file carries its own copyright banner, which is why these are the
unmodified minified builds rather than a re-bundle.
