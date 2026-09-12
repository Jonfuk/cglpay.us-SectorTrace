# Synthetic map fixture

`synthetic-boundaries.pmtiles` contains one deliberately fictional rectangle
between longitudes -2 and -1 and latitudes 52 and 53. Its `authorities` vector
layer has `ons_code=E00000001` and `name=Example Authority`.

The single zoom-zero MVT tile was encoded from these coordinates at extent
4096, then wrapped using `pipeline.pmtiles._write_archive`. MapLibre overzooms
the tile. This fixture tests the actual PMTiles range reader, MVT decoding,
boundary painting and exact-ID selection without a source request or database.
It is not a real authority boundary and must never be used as evidence.

Browser tests read this fixed input and write screenshots only to temporary
directories. The separate PMTiles unit fixture checks shared-payload runs.
