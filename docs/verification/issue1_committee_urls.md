# Committee portal URLs from issue #1 — verification result

Every URL in [issue #1](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues/1) was
fetched once through the pipeline's own HTTP client (real User-Agent with a contact
address, robots respected, per-host rate limit). This records what each one did.

- **104 of 313 responded** and were written to `authority_url_overrides`.
- **209 did not** and were not stored. Their review items remain pending.

A URL that does not respond is worse than an absent one: Module 10 would search a
host that isn't there, find nothing, and record the authority as publishing nothing.

## Not stored

### does not exist — 138

hostname does not resolve — the URL is wrong.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Amber Valley | `E07000032` | https://democracy.ambervalley.gov.uk |
| Ashford | `E07000105` | https://democracy.ashford.gov.uk |
| Babergh | `E07000200` | https://democracy.baberghmidsuffolk.gov.uk |
| Barnsley | `E08000038` | https://democracy.barnsley.gov.uk |
| Basildon | `E07000066` | https://democracy.basildon.gov.uk |
| Bassetlaw | `E07000171` | https://democracy.bassetlaw.gov.uk |
| Bedford | `E06000055` | https://democracy.bedford.gov.uk |
| Birmingham | `E08000025` | https://cmis.birmingham.gov.uk/cmis5 |
| Bolsover | `E07000033` | https://democracy.bolsover.gov.uk |
| Bolton | `E08000001` | https://democracy.bolton.gov.uk |
| Bracknell Forest | `E06000036` | https://democracy.bracknell-forest.gov.uk |
| Bradford | `E08000032` | https://democracy.bradford.gov.uk |
| Braintree | `E07000067` | https://democracy.braintree.gov.uk |
| Brentwood | `E07000068` | https://democracy.brentwood.gov.uk |
| Broadland | `E07000144` | https://democracy.broadland.gov.uk |
| Bromsgrove | `E07000234` | https://democracy.bromsgrove.gov.uk |
| Broxbourne | `E07000095` | https://democracy.broxbourne.gov.uk |
| Buckinghamshire | `E06000060` | https://democracy.buckinghamshire.gov.uk |
| Burnley | `E07000117` | https://democracy.burnley.gov.uk |
| Bury | `E08000002` | https://democracy.bury.gov.uk |
| Calderdale | `E08000033` | https://democracy.calderdale.gov.uk |
| Cannock Chase | `E07000192` | https://democracy.cannockchasedc.gov.uk |
| Castle Point | `E07000069` | https://democracy.castlepoint.gov.uk |
| Chelmsford | `E07000070` | https://democracy.chelmsford.gov.uk |
| Cherwell | `E07000177` | https://democracy.cherwell.gov.uk |
| Cheshire East | `E06000049` | https://moderation.cheshireeast.gov.uk |
| Cheshire West and Chester | `E06000050` | https://cmis.cheshirewestandchester.gov.uk/cmis5 |
| Chesterfield | `E07000034` | https://democracy.chesterfield.gov.uk |
| Chichester | `E07000225` | https://democracy.chichester.gov.uk |
| Colchester | `E07000071` | https://democracy.colchester.gov.uk |
| Cotswold | `E07000079` | https://democracy.cotswold.gov.uk |
| Coventry | `E08000026` | https://democracy.coventry.gov.uk |
| Cumberland | `E06000063` | https://democracy.cumberland.gov.uk |
| Dartford | `E07000107` | https://democracy.dartford.gov.uk |
| Doncaster | `E08000017` | https://democracy.doncaster.gov.uk |
| Dorset | `E06000059` | https://democracy.dorsetcouncil.gov.uk |
| Dover | `E07000108` | https://democracy.dover.gov.uk |
| Ealing | `E09000009` | https://democracy.ealing.gov.uk |
| East Cambridgeshire | `E07000009` | https://democracy.eastcambs.gov.uk |
| East Hampshire | `E07000085` | https://democracy.easthants.gov.uk |
| East Riding of Yorkshire | `E06000011` | https://democracy.eastriding.gov.uk |
| East Staffordshire | `E07000193` | https://democracy.eaststaffsbc.gov.uk |
| Eastleigh | `E07000086` | https://democracy.eastleigh.gov.uk |
| Elmbridge | `E07000207` | https://democracy.elmbridge.gov.uk |
| Epping Forest | `E07000072` | https://democracy.eppingforestdc.gov.uk |
| Erewash | `E07000036` | https://democracy.erewash.gov.uk |
| Exeter | `E07000041` | https://democracy.exeter.gov.uk |
| Fareham | `E07000087` | https://democracy.fareham.gov.uk |
| Fenland | `E07000010` | https://democracy.fenland.gov.uk |
| Folkestone and Hythe | `E07000112` | https://democracy.folkestone-hythe.gov.uk |
| Forest of Dean | `E07000080` | https://democracy.forestofdean.gov.uk |
| Fylde | `E07000119` | https://democracy.fylde.gov.uk |
| Great Yarmouth | `E07000145` | https://democracy.great-yarmouth.gov.uk |
| Greenwich | `E09000011` | https://democracy.royalgreenwich.gov.uk |
| Hackney | `E09000012` | https://democracy.hackney.gov.uk |
| Halton | `E06000006` | https://democracy.halton.gov.uk |
| Harborough | `E07000131` | https://democracy.harborough.gov.uk |
| Haringey | `E09000014` | https://democracy.haringey.gov.uk |
| Harlow | `E07000073` | https://democracy.harlow.gov.uk |
| Harrow | `E09000015` | https://cmispublic.harrow.gov.uk/cmis5 |
| Hart | `E07000089` | https://democracy.hart.gov.uk |
| Hartlepool | `E06000001` | https://democracy.hartlepool.gov.uk |
| Hastings | `E07000062` | https://democracy.hastings.gov.uk |
| Havant | `E07000090` | https://democracy.havant.gov.uk |
| Herefordshire, County of | `E06000019` | https://democracy.herefordshire.gov.uk |
| Hertsmere | `E07000098` | https://democracy.hertsmere.gov.uk |
| Hillingdon | `E09000017` | https://democracy.hillingdon.gov.uk |
| Hinckley and Bosworth | `E07000132` | https://democracy.hinckley-bosworth.gov.uk |
| Horsham | `E07000227` | https://democracy.horsham.gov.uk |
| Isle of Wight | `E06000046` | https://democracy.iow.gov.uk |
| Isles of Scilly | `E06000053` | https://democracy.scilly.gov.uk |
| Kensington and Chelsea | `E09000020` | https://democracy.rbkc.gov.uk |
| Knowsley | `E08000011` | https://democracy.knowsley.gov.uk |
| Lancaster | `E07000121` | https://democracy.lancaster.gov.uk |
| Lincoln | `E07000138` | https://democracy.lincoln.gov.uk |
| Liverpool | `E08000012` | https://csuite.liverpool.gov.uk/cmis5 |
| Mansfield | `E07000174` | https://democracy.mansfield.gov.uk |
| Mid Sussex | `E07000228` | https://democracy.midsussex.gov.uk |
| Middlesbrough | `E06000002` | https://electorate.middlesbrough.gov.uk |
| Mole Valley | `E07000210` | https://democracy.molevalley.gov.uk |
| Newcastle-under-Lyme | `E07000195` | https://democracy.newcastle-staffs.gov.uk |
| North Norfolk | `E07000147` | https://democracy.north-norfolk.gov.uk |
| North Somerset | `E06000024` | https://democracy.n-somerset.gov.uk |
| North Warwickshire | `E07000218` | https://democracy.northwarwicks.gov.uk |
| North West Leicestershire | `E07000134` | https://democracy.nwleicestershire.gov.uk |
| Northumberland | `E06000057` | https://democracy.northumberland.gov.uk |
| Nottinghamshire | `E10000024` | https://democracy.nottinghamshire.gov.uk |
| Nuneaton and Bedworth | `E07000219` | https://democracy.nuneatonandbedworth.gov.uk |
| Oadby and Wigston | `E07000135` | https://democracy.oadby-wigston.gov.uk |
| Oldham | `E08000004` | https://democracy.oldham.gov.uk |
| Pendle | `E07000122` | https://democracy.pendle.gov.uk |
| Preston | `E07000123` | https://democracy.preston.gov.uk |
| Redcar and Cleveland | `E06000003` | https://democracy.redcar-cleveland.gov.uk |
| Redditch | `E07000236` | https://democracy.redditchbc.gov.uk |
| Richmond upon Thames | `E09000027` | https://democracy.richmond.gov.uk |
| Rochford | `E07000075` | https://democracy.rochford.gov.uk |
| Rossendale | `E07000125` | https://democracy.rossendale.gov.uk |
| Rother | `E07000064` | https://democracy.rother.gov.uk |
| Rugby | `E07000220` | https://democracy.rugby.gov.uk |
| Rutland | `E06000017` | https://democracy.rutland.gov.uk |
| Sandwell | `E08000028` | https://cmis.sandwell.gov.uk/cmis5 |
| Sefton | `E08000014` | https://democracy.sefton.gov.uk |
| Sevenoaks | `E07000111` | https://democracy.sevenoaks.gov.uk |
| South Derbyshire | `E07000039` | https://democracy.southderbyshire.gov.uk |
| South Hams | `E07000044` | https://democracy.southhams.gov.uk |
| South Kesteven | `E07000141` | https://democracy.southkesteven.gov.uk |
| South Ribble | `E07000126` | https://democracy.southribble.gov.uk |
| South Staffordshire | `E07000196` | https://democracy.sstaffs.gov.uk |
| South Tyneside | `E08000023` | https://democraticservices.southtyneside.gov.uk |
| Southampton | `E06000045` | https://democracy.southampton.gov.uk |
| St. Helens | `E08000013` | https://democracy.sthelens.gov.uk |
| Stafford | `E07000197` | https://democracy.staffordbc.gov.uk |
| Staffordshire | `E10000028` | https://mycouncil.staffordshire.gov.uk |
| Stroud | `E07000082` | https://democracy.stroud.gov.uk |
| Sunderland | `E08000024` | https://agendas.sunderland.gov.uk |
| Surrey Heath | `E07000214` | https://democracy.surreyheath.gov.uk |
| Tameside | `E08000008` | https://democracy.tameside.gov.uk |
| Tandridge | `E07000215` | https://democracy.tandridge.gov.uk |
| Tendring | `E07000076` | https://democracy.tendringdc.gov.uk |
| Tewkesbury | `E07000083` | https://democracy.tewkesbury.gov.uk |
| Three Rivers | `E07000102` | https://democracy.threerivers.gov.uk |
| Tonbridge and Malling | `E07000115` | https://democracy.tnmalling.gov.uk |
| Torbay | `E06000027` | https://democracy.torbay.gov.uk |
| Trafford | `E08000009` | https://democracy.trafford.gov.uk |
| Uttlesford | `E07000077` | https://democracy.uttlesford.gov.uk |
| Wakefield | `E08000036` | https://mgov.wakefield.gov.uk |
| Warrington | `E06000007` | https://democracy.warrington.gov.uk |
| Warwick | `E07000222` | https://democracy.warwickdc.gov.uk |
| Watford | `E07000103` | https://democracy.watford.gov.uk |
| Waverley | `E07000216` | https://democracy.waverley.gov.uk |
| Wealden | `E07000065` | https://democracy.wealden.gov.uk |
| West Devon | `E07000047` | https://democracy.westdevon.gov.uk |
| West Oxfordshire | `E07000181` | https://status.westoxon.gov.uk |
| Woking | `E07000217` | https://democracy.woking.gov.uk |
| Wolverhampton | `E08000031` | https://democracy.wolverhampton.gov.uk |
| Worcester | `E07000237` | https://democracy.worcester.gov.uk |
| Wyre | `E07000128` | https://democracy.wyre.gov.uk |
| Wyre Forest | `E07000239` | https://democracy.wyreforestdc.gov.uk |

### blocked by robots — 26

site exists; robots.txt disallows automated access.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Bath and North East Somerset | `E06000022` | https://democracy.bathnes.gov.uk |
| Bexley | `E09000004` | https://democracy.bexley.gov.uk |
| Blackpool | `E06000009` | https://democracy.blackpool.gov.uk |
| Bromley | `E09000006` | https://cds.bromley.gov.uk |
| Canterbury | `E07000106` | https://democracy.canterbury.gov.uk |
| City of London | `E09000001` | https://democracy.cityoflondon.gov.uk |
| Cornwall | `E06000052` | https://democracy.cornwall.gov.uk |
| Dacorum | `E07000096` | https://democracy.dacorum.gov.uk |
| Derbyshire Dales | `E07000035` | https://democracy.derbyshiredales.gov.uk |
| East Sussex | `E10000011` | https://democracy.eastsussex.gov.uk |
| Hertfordshire | `E10000015` | https://democracy.hertfordshire.gov.uk |
| Hounslow | `E09000018` | https://democraticservices.hounslow.gov.uk |
| Lambeth | `E09000022` | https://moderngov.lambeth.gov.uk |
| Newcastle upon Tyne | `E08000021` | https://democracy.newcastle.gov.uk |
| North Kesteven | `E07000139` | https://democracy.n-kesteven.gov.uk |
| Redbridge | `E09000026` | https://moderngov.redbridge.gov.uk |
| South Gloucestershire | `E06000025` | https://council.southglos.gov.uk |
| Southwark | `E09000028` | https://moderngov.southwark.gov.uk |
| Stockport | `E08000007` | https://democracy.stockport.gov.uk |
| Stoke-on-Trent | `E06000021` | https://moderngov.stoke.gov.uk |
| Stratford-on-Avon | `E07000221` | https://democracy.stratford.gov.uk |
| Swale | `E07000113` | https://democracy.swale.gov.uk |
| Waltham Forest | `E09000031` | https://democracy.walthamforest.gov.uk |
| Wandsworth | `E09000032` | https://democracy.wandsworth.gov.uk |
| Welwyn Hatfield | `E07000241` | https://democracy.welhat.gov.uk |
| Wiltshire | `E06000054` | https://cms.wiltshire.gov.uk |

### 403 — 16

site exists; refused this client.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Barnet | `E09000003` | https://barnet.moderngov.co.uk |
| Camden | `E09000007` | https://democracy.camden.gov.uk |
| Huntingdonshire | `E07000011` | https://democracy.huntingdonshire.gov.uk |
| Leeds | `E08000035` | https://democracy.leeds.gov.uk |
| Lincolnshire | `E10000019` | https://lincolnshire.moderngov.co.uk |
| Milton Keynes | `E06000042` | https://milton-keynes.moderngov.co.uk |
| North Devon | `E07000043` | https://democracy.northdevon.gov.uk |
| North Northamptonshire | `E06000061` | https://northnorthants.moderngov.co.uk |
| Norwich | `E07000148` | https://cmis.norwich.gov.uk/live |
| South Cambridgeshire | `E07000012` | https://scambs.moderngov.co.uk |
| St Albans | `E07000240` | https://stalbans.moderngov.co.uk |
| West Sussex | `E10000032` | https://westsussex.moderngov.co.uk |
| Westmorland and Furness | `E06000064` | https://westmorlandandfurness.moderngov.co.uk |
| Windsor and Maidenhead | `E06000040` | https://rbwm.moderngov.co.uk |
| Wokingham | `E06000041` | https://wokingham.moderngov.co.uk |
| Worcestershire | `E10000034` | https://worcestershire.moderngov.co.uk |

### unreachable — 11

HTTPStatusError.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Central Bedfordshire | `E06000056` | https://centralbedfordshire.moderngov.co.uk |
| East Suffolk | `E07000244` | https://eastsuffolk.moderngov.co.uk |
| Leicester | `E06000016` | https://cabinet.leicester.gov.uk |
| Malvern Hills | `E07000235` | https://malvernhills.moderngov.co.uk |
| Norfolk | `E10000020` | https://norfolk.moderngov.co.uk |
| Salford | `E08000006` | https://democracy.salford.gov.uk |
| Shropshire | `E06000051` | https://shropshire.moderngov.co.uk |
| Swindon | `E06000030` | https://swindon.moderngov.co.uk |
| West Northamptonshire | `E06000062` | https://northamptonshire.moderngov.co.uk |
| West Suffolk | `E07000245` | https://westsuffolk.moderngov.co.uk |
| Wychavon | `E07000238` | https://wychavon.moderngov.co.uk |

### unreachable — 9

ConnectError.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Boston | `E07000136` | https://democracy.boston.gov.uk |
| East Lindsey | `E07000137` | https://democracy.e-lindsey.gov.uk |
| Gravesham | `E07000109` | https://democracy.gravesham.gov.uk |
| Kingston upon Hull, City of | `E06000010` | https://cmis.hullcc.gov.uk/cmis |
| Newham | `E09000025` | https://mgov.newham.gov.uk |
| North East Lincolnshire | `E06000012` | https://democracy.nelincs.gov.uk |
| Plymouth | `E06000026` | https://democracy.plymouth.gov.uk |
| South Holland | `E07000140` | https://democracy.sholland.gov.uk |
| Torridge | `E07000046` | https://democracy.torridge.gov.uk |

### no response — 6

host exists but did not answer.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Barking and Dagenham | `E09000002` | https://modgov.lbbd.gov.uk/Internet |
| Cambridgeshire | `E10000003` | https://cmis.cambridgeshire.gov.uk/cmis5 |
| Charnwood | `E07000130` | https://democracy.charnwood.gov.uk |
| Enfield | `E09000010` | https://democracy.enfield.gov.uk |
| Stockton-on-Tees | `E06000004` | https://egenda.stockton.gov.uk |
| Tamworth | `E07000199` | https://democracy.tamworth.gov.uk |

### HTTP 404 — 2

site answered with an error.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| County Durham | `E06000047` | https://democracy.durham.gov.uk |
| Essex | `E10000012` | https://cmis.essex.gov.uk/cmis5 |

### unreachable — 1

RemoteProtocolError.

| Authority | ONS code | URL in issue |
| --- | --- | --- |
| Reigate and Banstead | `E07000211` | https://democracy.reigate-banstead.gov.uk |

## Stored

| Authority | ONS code | URL | system probed |
| --- | --- | --- | --- |
| Adur | `E07000223` | https://democracy.adur-worthing.gov.uk | moderngov |
| Ashfield | `E07000170` | https://democracy.ashfield.gov.uk | moderngov |
| Basingstoke and Deane | `E07000084` | https://democracy.basingstoke.gov.uk | moderngov |
| Blaby | `E07000129` | https://democracy.blaby.gov.uk | moderngov |
| Blackburn with Darwen | `E06000008` | https://democracy.blackburn.gov.uk | moderngov |
| Bournemouth, Christchurch and Poole | `E06000058` | https://democracy.bcpcouncil.gov.uk | moderngov |
| Breckland | `E07000143` | https://democracy.breckland.gov.uk | moderngov |
| Brent | `E09000005` | https://democracy.brent.gov.uk | moderngov |
| Brighton and Hove | `E06000043` | https://democracy.brighton-hove.gov.uk | moderngov |
| Bristol, City of | `E06000023` | https://democracy.bristol.gov.uk | moderngov |
| Broxtowe | `E07000172` | https://democracy.broxtowe.gov.uk | moderngov |
| Cambridge | `E07000008` | https://democracy.cambridge.gov.uk | moderngov |
| Cheltenham | `E07000078` | https://democracy.cheltenham.gov.uk | moderngov |
| Chorley | `E07000118` | https://democracy.chorley.gov.uk | moderngov |
| Crawley | `E07000226` | https://democracy.crawley.gov.uk | moderngov |
| Croydon | `E09000008` | https://democracy.croydon.gov.uk | moderngov |
| Darlington | `E06000005` | https://democracy.darlington.gov.uk | moderngov |
| Derby | `E06000015` | https://www.derby.gov.uk/council-and-democracy | unknown |
| Derbyshire | `E10000007` | https://democracy.derbyshire.gov.uk | moderngov |
| Devon | `E10000008` | https://democracy.devon.gov.uk | moderngov |
| Dudley | `E08000027` | https://cmis.dudley.gov.uk/cmis5 | unknown |
| East Devon | `E07000040` | https://democracy.eastdevon.gov.uk | moderngov |
| East Hertfordshire | `E07000242` | https://democracy.eastherts.gov.uk | moderngov |
| Eastbourne | `E07000061` | https://democracy.lewes-eastbourne.gov.uk | moderngov |
| Epsom and Ewell | `E07000208` | https://democracy.epsom-ewell.gov.uk | moderngov |
| Gateshead | `E08000037` | https://democracy.gateshead.gov.uk | moderngov |
| Gedling | `E07000173` | https://democracy.gedling.gov.uk | moderngov |
| Gloucester | `E07000081` | https://democracy.gloucester.gov.uk | moderngov |
| Gloucestershire | `E10000013` | https://glostext.gloucestershire.gov.uk | moderngov |
| Gosport | `E07000088` | https://democracy.gosport.gov.uk | moderngov |
| Guildford | `E07000209` | https://democracy.guildford.gov.uk | moderngov |
| Hammersmith and Fulham | `E09000013` | https://democracy.lbhf.gov.uk | moderngov |
| Hampshire | `E10000014` | https://democracy.hants.gov.uk | moderngov |
| Havering | `E09000016` | https://democracy.havering.gov.uk | moderngov |
| High Peak | `E07000037` | https://democracy.highpeak.gov.uk | moderngov |
| Hyndburn | `E07000120` | https://democracy.hyndburnbc.gov.uk | moderngov |
| Ipswich | `E07000202` | https://democracy.ipswich.gov.uk | moderngov |
| Islington | `E09000019` | https://democracy.islington.gov.uk | moderngov |
| Kent | `E10000016` | https://democracy.kent.gov.uk | moderngov |
| King's Lynn and West Norfolk | `E07000146` | https://democracy.west-norfolk.gov.uk | moderngov |
| Kingston upon Thames | `E09000021` | https://kingston.moderngov.co.uk | moderngov |
| Kirklees | `E08000034` | https://democracy.kirklees.gov.uk | moderngov |
| Lancashire | `E10000017` | https://council.lancashire.gov.uk | moderngov |
| Leicestershire | `E10000018` | https://politics.leics.gov.uk | moderngov |
| Lewes | `E07000063` | https://democracy.lewes-eastbourne.gov.uk | moderngov |
| Lewisham | `E09000023` | https://councilmeetings.lewisham.gov.uk | moderngov |
| Lichfield | `E07000194` | https://democracy.lichfielddc.gov.uk | moderngov |
| Luton | `E06000032` | https://democracy.luton.gov.uk/cmis5public | unknown |
| Maidstone | `E07000110` | https://meetings.maidstone.gov.uk | moderngov |
| Maldon | `E07000074` | https://democracy.maldon.gov.uk | moderngov |
| Manchester | `E08000003` | https://democracy.manchester.gov.uk | moderngov |
| Medway | `E06000035` | https://democracy.medway.gov.uk | moderngov |
| Melton | `E07000133` | https://democracy.melton.gov.uk | moderngov |
| Merton | `E09000024` | https://democracy.merton.gov.uk | moderngov |
| Mid Devon | `E07000042` | https://democracy.middevon.gov.uk | moderngov |
| Newark and Sherwood | `E07000175` | https://democracy.newark-sherwooddc.gov.uk | moderngov |
| North Hertfordshire | `E07000099` | https://democracy.north-herts.gov.uk | moderngov |
| North Lincolnshire | `E06000013` | https://democracy.northlincs.gov.uk | unknown |
| North Tyneside | `E08000022` | https://democracy.northtyneside.gov.uk | moderngov |
| North Yorkshire | `E06000065` | https://edemocracy.northyorks.gov.uk | moderngov |
| Nottingham | `E06000018` | https://committee.nottinghamcity.gov.uk | moderngov |
| Oxford | `E07000178` | https://mycouncil.oxford.gov.uk | moderngov |
| Oxfordshire | `E10000025` | https://mycouncil.oxfordshire.gov.uk | moderngov |
| Peterborough | `E06000031` | https://democracy.peterborough.gov.uk | moderngov |
| Portsmouth | `E06000044` | https://democracy.portsmouth.gov.uk | moderngov |
| Reading | `E06000038` | https://democracy.reading.gov.uk | moderngov |
| Ribble Valley | `E07000124` | https://democracy.ribblevalley.gov.uk | moderngov |
| Rochdale | `E08000005` | https://democracy.rochdale.gov.uk | moderngov |
| Rotherham | `E08000018` | https://moderngov.rotherham.gov.uk | moderngov |
| Runnymede | `E07000212` | https://democracy.runnymede.gov.uk | moderngov |
| Rushcliffe | `E07000176` | https://democracy.rushcliffe.gov.uk | moderngov |
| Rushmoor | `E07000092` | https://democracy.rushmoor.gov.uk | moderngov |
| Sheffield | `E08000039` | https://democracy.sheffield.gov.uk | moderngov |
| Slough | `E06000039` | https://democracy.slough.gov.uk | moderngov |
| Solihull | `E08000029` | https://democracy.solihull.gov.uk | moderngov |
| Somerset | `E06000066` | https://democracy.somerset.gov.uk | moderngov |
| South Norfolk | `E07000149` | https://democracy.southnorfolkandbroadland.gov.uk | moderngov |
| South Oxfordshire | `E07000179` | https://democratic.southoxon.gov.uk | moderngov |
| Southend-on-Sea | `E06000033` | https://democracy.southend.gov.uk | moderngov |
| Spelthorne | `E07000213` | https://democracy.spelthorne.gov.uk | moderngov |
| Staffordshire Moorlands | `E07000198` | https://democracy.staffsmoorlands.gov.uk | moderngov |
| Stevenage | `E07000243` | https://democracy.stevenage.gov.uk | moderngov |
| Suffolk | `E10000029` | https://committeeminutes.suffolk.gov.uk | unknown |
| Surrey | `E10000030` | https://mycouncil.surreycc.gov.uk | moderngov |
| Sutton | `E09000029` | https://moderngov.sutton.gov.uk | moderngov |
| Teignbridge | `E07000045` | https://democracy.teignbridge.gov.uk | moderngov |
| Telford and Wrekin | `E06000020` | https://democracy.telford.gov.uk | moderngov |
| Test Valley | `E07000093` | https://democracy.testvalley.gov.uk | moderngov |
| Thanet | `E07000114` | https://democracy.thanet.gov.uk | moderngov |
| Thurrock | `E06000034` | https://democracy.thurrock.gov.uk | moderngov |
| Tower Hamlets | `E09000030` | https://democracy.towerhamlets.gov.uk | moderngov |
| Tunbridge Wells | `E07000116` | https://democracy.tunbridgewells.gov.uk | moderngov |
| Vale of White Horse | `E07000180` | https://democratic.whitehorsedc.gov.uk | moderngov |
| Walsall | `E08000030` | https://cmispublic.walsall.gov.uk/cmis | unknown |
| Warwickshire | `E10000031` | https://democracy.warwickshire.gov.uk | moderngov |
| West Berkshire | `E06000037` | https://decisionmaking.westberks.gov.uk | moderngov |
| West Lancashire | `E07000127` | https://democracy.westlancs.gov.uk | moderngov |
| West Lindsey | `E07000142` | https://democracy.west-lindsey.gov.uk | moderngov |
| Westminster | `E09000033` | https://committees.westminster.gov.uk | moderngov |
| Wigan | `E08000010` | https://democracy.wigan.gov.uk | moderngov |
| Winchester | `E07000094` | https://democracy.winchester.gov.uk | moderngov |
| Wirral | `E08000015` | https://democracy.wirral.gov.uk | moderngov |
| Worthing | `E07000229` | https://democracy.adur-worthing.gov.uk | moderngov |
| York | `E06000014` | https://democracy.york.gov.uk | moderngov |

## Subsequently verified outside issue #1

The issue-#1 candidate for Herefordshire was not stored. On 2026-08-13, the
official council homepage linked to the following committee portal. The link
was fetched and its ModernGov signature was confirmed through the pipeline's
HTTP client before it was written to `authority_url_overrides`.

| Authority | ONS code | URL | system probed |
| --- | --- | --- | --- |
| Herefordshire, County of | `E06000019` | https://councillors.herefordshire.gov.uk | moderngov |
