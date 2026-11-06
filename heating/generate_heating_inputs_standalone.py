#!/usr/bin/env python3
"""Download heating sources and create model-ready H2RES inputs.

Creates:
  flex_tech_heat, flex_tech_DH
  thermal_tech, thermal_tech_DH
  solar_indv, solar_DH
  heat_demand_*_indv.csv and heat_demand_*_DH.csv

The pipeline downloads/caches GISCO NUTS, JRC-IDEES, five JRC Energy Atlas
fuel rasters, Eurostat population, Hotmaps heat density and CHP locations.
By default it requests eight inhabited grid-point temperature series per NUTS3
region from Open-Meteo and population-weights them; a CDS NetCDF is supported.
Companion paper-method modules run the embedded calculator, verify its sources
and create model-ready sheets and curves.
"""

from __future__ import annotations

import argparse
import gzip
import base64
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))
YEAR = 2020

NUTS_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/"
    "NUTS_RG_01M_2021_4326_LEVL_3.geojson"
)
IDEES_URL = "https://zenodo.org/records/15895830/files/JRC-IDEES-2021.zip?download=1"
POP_URL = (
    "https://zenodo.org/records/17913230/files/"
    "ESTAT_OBS-VALUE-T_2021_V2.tiff?download=1"
)
HOTMAPS_URL = (
    "https://gitlab.com/hotmaps/buildings/heat/heat_tot_curr_density/"
    "-/raw/master/data/heat_tot_curr_density.tif"
)
EIGL_BASE_URL = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EIGL-Data/RASTER"
EIGL_FILES = (
    "gas_oth_demand_2019.tif", "oil_oth_demand_2019.tif",
    "solid_oth_demand_2019.tif", "renewables_oth_demand_2019.tif",
    "electricity_oth_demand_2019.tif",
)

# Filled from the companion raw calculator at build time. Keeping it compressed
# makes this script genuinely copyable without changing the audited algorithm.
RAW_CALCULATOR_GZ_B64 = (
    'H4sIAAAAAAAC/+19a3fbRpLod/6KHuScNWCTkGQnngwzzD0e2Ymz49g+trM+uxwuDkQ2RYxJgAOAkhit9rdvPfqJB0Unnrv3w/WZ'
    'iQj0q7q6uqq6uqrw1R9OdlV5cpHlJzK/Ett9vSryJ4OvxOjhSMyLRZZfjsWuXo6+xTeDIAgG+a6uniQrmdbJqtiV632yLbYvnz9P'
    'lju5fvHTj6/gdb1Jt9Xzl8nV1/F2Pxj8WKTrwQj+Dc5LaCfF618+vH8iuLnArsRCbtJ8IS72Ars5qeV8lRfr4nIvrleylOOBECPx'
    'Oq2zIk/Xoi7qdF0BgBsplmWxEf/67nz00/MXL96L8J2ssoXM6wzqPRIfZAm/yv134v1LeHz+8uPJy6IW1wBFGVGnz/J8B1UZJOpY'
    'VFsAcyGySmzSLAcQ3755C41hkiKs5WYry7TelWroF++efcM94eRFmVbQdSVSKN9VciHevH7179CvqFbpVoqH11m9yvJRKS9hKjRZ'
    'LCll9VCEOUDGU+MOn2dVXWbzmlAES6HAo2F5tgFXudjVMBLWCoYAfUqTT9frYk4Y4xYveVk0vvMqq/cK3MHgza7ewsKKsNjViwxQ'
    'M2r8A4BSwlTCBPDn8/Pvkz//O/z7Pp5XV8L795Wqq9dTAMoYw9CNopqjulEk0upGhN/+8enpKrJQEWoOd2qgYjSGgCDqtoq64Duq'
    'QwXf4Q7n6TadA7ITpJ01UF7vrL9yZngj7CYY61lurldDppchVE0/wYtkk+VDHAN+i/AsfnwTDQavi1pWvIaDEZFvtds4nWe0ebZE'
    'NldZqsgAyL36FHOD0bXMLldYPofNVBbZwm9OtL0sSqJ/sS2yvBZVCvMDOsUucLMwdsbQ7U14OhQXaSUJB0DaHx5vzqPvbC+wO7dl'
    'sczWEhvDNtWPwH7yDGpskAgWcpnu1nVMjGhAVJ0A38HNmCQi22yLskZUwXIg3VeDgX5XXm7TspL6eZVWq3V2oR//XhU5dwd7Bwt0'
    'X2/hkQvq/RZ3oHr/HHblULyCzTcUH3bbtTQjlWaMOtuY34AH6DX2YFDvSvmPnaxq00G+22z3Iq1EvtWvtsAa4QX8b7vQ7y5lYV9f'
    '2ve8klnBUOuneCmJZVXCNt/IutwnuOSNutdZviiuTVUsTC6KXb6ouCJxsvU+1n3oisBdEEcakpu0LFOayQ0wGKiHTFzoytv9HLqE'
    'twN5M5fbWrygP7BqXM2Ui4l4XeSAYJRKh/5B+TmseZ3mwMdOkGzq6t42f/3w5kXy4U3y88eXMNDZ2dMnp/EpbsQz8akuJL2Lnz4R'
    'P35c6XLx88fV4MXb9z8mH569+/HFB3j/5PTJNwQgc2WZL0ZA2chpUYKqzYIyoC624gLY8ieBpIAEFYKsuZIIcjqfk+ACLrKHrrJ8'
    'vt5hc5hV8Qn+npyj0MIfsp7HUO6LBZAZNHry4vXzX96/SN5/ePM2efXsLy9evQcIp4TU4D1wIqnbBUP35bwo1s7LjzhYs6YRnfqF'
    'As08Kgj187OshH7zRYbr6rx/hazFrbcFvpHmc1npN29qEPuIt8YbQK1+Oxv88AtMLnnzywc7wcvUNCiytf45BwVE/77ICqB5UwuI'
    'GDve2ApyLecodknHsVMljWcLm1O/WCjpnFgkzY6i0pdyDay0Gmuu+yvpNMigHwEj3bY57719Al8USbpcZrlMbvYJ7dhyHtZlmlfI'
    'O4eihA0NUqIAMuH9BRwUdsuVRJZRXJ9AiaD9WiGd3pzs9dOOqJT7FqZDEc4lCDsEEGYSxciPsdcSVgKHimFm+60M8228XBdp/fTr'
    'CCZ3Gn9DteZQC0E5XOsGapkB4zmU2KdUPBT+mwt4U1K7vddu6dVatNpJ066UwCFzcTMUoLISSmlhEliYBDgtqrmJXpGQW9D6JSgz'
    'xrC3SyYMZIsJcgR+zItFWqfJVboGNj9maTGl6Q5FHMczgDYc/Qn+xafDiJvUqCUnv8qySNIq4Q7G4gI2KFT+Aba6HA4iMfre78x7'
    'oD+zmVlr+vuOZxgiqRVLTX4MGfAT1JsJ+mE3GSLLUW3O372P4gEvpi419S/2ja5D6G63JpEMrVyIUBu2gqfYyjx0kBqh8KjKOc/C'
    '4JZlEaDCYDpW4klXAwkGxY7gCh86LYd2+SfQe2yeokYH8N+4xCZJsVxWsq7CSD2vZX5Zr+B5MLC62/k62woWnriJFA7kTQ0YEiHL'
    'PRBOpO+w/l8JULcJ7aryvIAdmV7KodOtjC9jge8rCeiAWmVWF2UmQcuEUdIrxD0oVajMg7xB0ecJdwENirKKTY9GEut/B6X/R3r0'
    '6lvkZLT9gV3CXEKuiYoe/A/xep0t6hX/XBFtRBbB3ULfThqofH2Rzj+NRbYU7jCge+YPQKG7SrN1erGWSJRwoqrMBARiCip6HQK3'
    'OQWYlSIK/YUIPrzFlXXAol1dXHfUhbcddaGHM6yb5aEz40b/wG/wiQrbY7ntGU2tQVUHLSTaxQhDhJrY/Fk0BO4M8yV2fxZ5JPoS'
    'GBngTK9xvYKjIInUrSKhdElkCJRMqpxuCYtwKUGprkuEaygCmgwcNk8j8eeJOBVA0n4FBtbW8Bd47u1eI+c81DCzAnUM5kPsLJzH'
    'N5FibfB7704NpBV0iTjETRCeDdUcJwQN7gO5mBDrjDqkjjtP6Cmusl9B9VPzoheo8k5PZx0vz/jlP2d+ZpUTK3onanPh9OxrRLuD'
    'D5xxopnLxOcIoQfHVKntoYE3mg29GtBNQnOdmFn7FSw7dQDyq2SkavAKDA05fih30rBADaPXDtgAnMR38xUsH9a2vTqLlqtZ/rc7'
    'a4sLkELAIieqHuzK7T60rZEb51fIRnxJ7YHBXfwLbDQktD9MoIVHNJ0S+3APsPDRoFUKRJlVoGtltcSKzorCKGgfggppvg+pQfRP'
    '3lTXggAiCxyPOETCH/qwoyTm5lAXVIvwOvJwU/3f2P9Wv2WYYXdkcJwIr5leLUA3UG2PlTr0ZZd6XY3ZDjO/aU72pgIF8joCqVvZ'
    'Qeb7ZrV9VzU1xQoZNqid833UUjxZqt2nblaExzEbJI7WOgm1SvWMlEYJ4OYLUv2N6vgf5niCBiAcjvaMMRrBzsHT8JiWUit2UB2R'
    'PJ39JjVvWaiBoG9nfh59XCgSaup+PfrfxRFa32/U/Bztr6X2dWpoOL1tsd5fuhqgVv0anLWhq/0Wfe1L6Wz3622fq2p9rrr1JVSu'
    'L6N2fa7q9c9QovQ+i0GAgxIXelzZoiuvs3wnm5AY9Jih7Vx/91i+CP8yqtlvUoM+TxVqqUNNTegobehIjailFbVK+3UfX/85Rge6'
    'Xw86Whe6Vx86UqE5Tqn5HYTnNvOEMcAxpbFmkd6jShQjICj80EQCYnmB1DhxqfEY+x7diLj3hPpeBKT/y+fPj7Pm0VVBgqIyAXKV'
    'RVI/3oR1WgKDGNO1RJ+4fodXl0UOAiVFyhFvoIvRz9iF2MsU5DYc90q5TbMSaq33otrgtVVWFXgztRCX6bYyUhxpAAgGr0diwADI'
    'UYaAdnJSg4wLZc7XxJOArokDxSfVxdiEuoihSRjwK2Bmt3dcBy9Iqhpwg5rCdhHXRQK1Jb4OuTI3xBfQbDoD9srGjEkwL2Q5lwF3'
    'pMxMRGxpxQvodWDXInm80V21F1dRpGUKIOxD7jxCIsdHC7QlQ9g1bk2kaNhCdEU5FN/+8duvvaow06zKU7cnon6u5JB/mWaVFO92'
    'OdZ8gRMPl8FPOW8tZ1mR3kaveF2rLegUZBS55aW6C8y8XBjhyIqA2cE+SblF9hE6cMUb2FcrrPs4Ev8i3JJFuqf3f4q8QwwvA/+Y'
    'YpezrsH/gIM/Pb13pnhFuYYpupP19pVEM1hjstTpJqvIbg0TchmQAkDDpGox9seOmeSZWAE6l7s1mkl1X8/e/qSnOE9zUcznO1Dz'
    'rmSOAOALvEe4xolouJ0e7RrhJozF84LIBBjXXOJdvbgui/zyBLXNVQFTuywzNLzCziRV+wL2NF+OGqnGUCV0S0ZMvQ71fJDH+Wcw'
    'v/b34vHXPpftWIC22vmbVkQEHR2Ftx5AdwbHuGurKOgRdMy25ILZxXsaS68p67Vb4mI+7MA+V8ViEgAHBtTD7l9nm6yePFU/kgV0'
    'SdrwJLiANQw6LAyGsjUEyKvoojbs5iK+bGvSXwwcN4z+H16BoXP7mKJIEGugTjjV1LAvxNN7lmlbIjH6ikUwtfDOhLNWC9GExIgi'
    'F6QQ2EbQ6NLOMc7TjbxrrpyS6Yx0dbL2BWrC2GJYSV4iNfDhGqc8FurIDACZ37iBxziFIZqaL4pK+nczvQfpH2Q9X53QMJYfDPlw'
    'rJx2QGSaBSY1Ak7Ga1CKxVLZw41oJmcKUBJSOmffmqkHeM9S7xYyAICDWwQ8frq8C4ZODVhLtwrMs1kFuHxZkzTmOjjnu9HpGfzP'
    'rQaaVavS2ePRE6+Skvtj0ZLDts6mWMh1hXWg/JtkDYjxxlnLK7o+whp5mrtluF9+BX0Hi378+YMquqP/srZg7RCo3yJThXVf6+sE'
    'ENQBMgaQbMAbAhra2ZsGxYtsXocO1qNGlWng9xygjcV/1X8Fo0g1WSKJNLW+trqrKXWoxmaiJDIluh02BjaU2rNj1ane5T5IefDa'
    'B1NdJSmdGnZJCFUaJ2Ngew0Ug55gMNxW7ju4hVlbj2moLhxRSvIxQ2anN813HcyOeirxyIfMhHYbSGrTHatTa91fu71SKVwZvkL3'
    'nEKLBTTciAp9EecF7NV03SHGq9hh2A8qp0c4H89X2ZXEiVyuiwvUBmCINkMYwhjo+yCymjX36xXoHiiyWvAx7pH0mbCAmQLf3uW7'
    'iq7MQLFZj+gwwPyPtYrGQjSQX/iMyV8Acxvn4j9g14E+zoZ7kS7utPWXWzIx3bPr9I5TbAN3GjGOYHDPfjR0OGhtw+O34BHbL3CJ'
    'NWhvP57GMdvu0JY7pDMEXQeEE8K88jgDmQIa5WL8t3wkAvFIBPQj/nuR5SGPqk4kSnQewExDdDqrMKYV5DdWcNKjI1P52cpb5Vjg'
    'Lp/Tc6fU7bdfPy+uczy8KsmLdEt7Hh2R8ZzsIAq364iIWm0MLW1BgiH1rOp6W41PTtSWHaXbjKzZI8JHDAR+cnWmS/8PItV1/Ivh'
    'gY7LMnSJmcGa0KE+NJh0yuLNJ3iBbdBPjE1BQCRZVSfFJ3rkyp8kHriVayNaph5/8zSEMWM1qDmhxyt5s8gugQbCaDp+fMrCkTZT'
    'gpoU2tbqUgHJR2i104augIaOQB9ep3PoeoRFiTprslKG4o+mdoLKge39LmFNIbkFgO9iNC4EA0dhViodTbBy1WRNt5OG62T8jv/6'
    'uxTqDMkDT5bV5Db4BVZ09OwSMIiKwuox7M6RctwaZfl2V4+gDJWTojw5i0+Du45jAGpiCW0N7ZToGs7SGvWbmr1kQFtGS+fXDS2/'
    '054P89Yk3Sm8DkjIDt16ocgdea/xzVGnguBAJyHril8v74aCdUL4+Z249bfhXdTdR5d1HARtY6HgkS9/+HlIJqBiV0/Ovj2lWyBt'
    'wOhBRLrHmdE5jOuxSbk9uGOxUo3adYC8yU9+oikOIU6q3XKZ3YQB0SXu2zrobRpfl3CqSy72tbx/HLNXeLR2vQuYy6eDly2dOlmL'
    'MKFGF4lp8gRt7Ek3ejutMD12Jk+CiFsY8y6I+Gaqa3zsMa7WUm7Dx+LhQw2Md1h2JpFVxAlwixG/PsgWfifodlhtKtOawAETbOQe'
    'J4kjNk+T9NJe1X7506Tr0afDEB5v9E4Pz4FdZzs4Nae1pzmzSsr++nWBYJ0AOKwBsndQRTqleICofEDof0DyMuEX86Iogbmg9ARu'
    'Tt7+LkSwkCTIzPyjOKtQoPmcnMDuPoyblkqXWms0GQwpjZx8AG9KksB4DAUtsXbG5UpXSqAFMEKA0KkfOTSPr9IyQ7UVthWg2rJ0'
    '5MjUDggRX/o301d5s/m4eQIyg1whG7qWZdhxraFBu8oP8IJ+UDpoPqAVzmV9/vwHEASy0kbGOkUbJRGIBjrWttIFmvgX1ZSGmQ2M'
    'aR4WbePKOTo8IzlAV1NtlA8saQSzsbudddVFGkNHDRQ5/WO9Qe/cTcVjpr9EtAscDSbvTR3rnFhQY6o0uVWwGbMxkJpWgKwdhdbT'
    'eaIp0S5QZBNiqanWVQMhj7SSa0cwdhhu6zx2jQFqkq53eAzipWoiCm10RaGHPp6SEJ3aCqcxcGLgdFhBZagJNAW69YnhB6kUNObY'
    'nI30I6gSQ2Oa1acypT7+FRVQuY75fN11KTzo05tYVwKVCOGfIbFPbomw74gGCOLJraaquzYd9HREV3jSKFLsBYLSA6+E/hoZClKc'
    'DaYwEo//+CQ++0ZJChVulawWCxU3GdbnY4exO/FRyVyJhz7e/1IFfizkZSmleED22AcYMnXjh1thpJXjnW8uOaFKttlt2AXIGRfq'
    '1+fH3XJyqIsKYznuTnOZ5YsEOXmCbhrwIG/CaiVlnSyWYzTpPwcm/gMcOqQjFwkH8NcXfDw67II9TF28fEe3I3DaxGYcfIlqeHEt'
    'TkU6L4sK493Wu01eKV+yquGIrrxQNDRxti7mU8DNeKao0LDAv4MYws5lvtvgeUGS/4fD3ls6PtCpvvO7isZHe2gQ/dG19VVEF3b4'
    'AufX0Yda2b8f6V/tDcm7/69yr5noebFbs85FAaSSkDrhQxvOnHFPqGIU0+bnJQZZL/PFDggKSsJ1eiHXSgHi1xU7qU3h1YxWFnWd'
    'sWVbUL+DP/HsWB/SLod4QqX6UYxxONsw0pLWpXW82qsQeXLXrEarKXe8lgSbmcUm3SbZQsqKgpqTukCHCm82WIMu/KCQXtFk4K/4'
    'Lwd4TV0/p1uFNQpjpY4o0KagsFsOGrVBz8Yk5yhVHmqQnYcZbDyMdoMjBRUONc8gjXlLBJcrFLV1LyPW78Glsi02Q5E1WCoKyglA'
    'RnxWCCCh3S0PWkC0Y6j0eD+mlRkixxsDOKhhbJfpPZhj9FKuAsJNUXsILDJdwQPHP2MgV28TG+qlwXmTrcXFbv4JKD5cwPLAUpyI'
    'V29/jBw84FsHvvX20n3K/rHLlpnEKFo4kq/lbnMIaIxd02OfF+n6pCpAd7Eo4UcPG+m6rzMq0739hcPfAPxS5vKa1FfTrY6Ns/3i'
    'XVzZ17GubhbNxNKJ8BOyn0qiDQk4CJD6Jq3nK00+uMPim3V1YxHoBOL1raStYUzyKlYPQ9lPhI7cM4GR4aFBv8Lg/8UVbqBFuyns'
    'ZkMGpvq5S3OtJo/MKwQH5jDPyrmKe8L+GoGFZuZpHxBH0KfuY34IMmc9+yHsG6wZDmkXO5c4htsj8RADky7pHv5zx+MA0IA8M8iZ'
    'Kiy2PF9DQxUfTYhK8GxCP5i52kcE+3Jvn0OO2G+cXlz+jr2aUNPOezu3diejHbRekKCRN3WZAvdjWVPRnQ0nHtBWBJDf66bHNysp'
    'rEeblw3jOveIMdBuQx6g0VLJ6wqjgNuvF6vrsSgu/i61FZ89A1SBslRY78SWXMSDTnaZF6UM7rfeY1j9lOSr/XUgktFQz21A0Bsp'
    'Aoo5ruoYQ7XhmBEArP67O6+3xZI9SsirjVAeWsQPHXxP7E9tW57Yc9d+ThPqVHMXS1ZpjUC16CVvogsJx3OUhUDY5PGzBsl4UqPb'
    'PvogpWvYCiAH8Z6QtQcGfHWdKGVi4vaI2qPVDmzBUIRryllAHYNWSSfHqa0wc5ae7s1d4pgBh8PmoR2WJ45h7YltxHVgAWO0B36S'
    '+yrUhY9EX4y6utIys9E6+HgoTmf6CMh0qO0WsIFoxSigXs9SKWmqpk9UTEp2B7OXQ7a4aZrzv6LkKdce2nVQv4N+vqHJFxb5Skvr'
    'Qr/S0Q4tAFWZeV0nSFEIfTiPOhXYObFxsrUs8cFaTmee0Sqz9xJ4ZlXL1zhKwNskc/XBihchm3Ur2Z71FpsqWJJ1hxOvg+zsHuM3'
    '8nJTvXUccHjp7Z11+QVdetxabPSNufMQUVpE2DEeibMhuSgulh04QZp2sFHOOiZ/QDXvVcyjQ6fB1sI4irpZjSYg7fNXUg29/dkx'
    'JOPed67CYw8gFNlZ72EIu3b5/cR9aIFmuuxcz/6pXznMAJYVmezsdx+vO+/hrugySB+5PzvspQt45ARGEpt9i+cizC4SdMKASX7Y'
    'iVY8FE5+Eh+gddclmd8a2VhV7TYgWtbIKPeUuaQZ2jnVC4N7Bf7Qfa9+x6F+sD1Uz4OWCX9XK7vfiq7lmuyYBEekhZVfxREjbO8w'
    'igWzRb25u+x81SqpaaLo61qtlJEmjDDC7kw+NfVwDFsRnnprgtqlaoatPh+1Wzebdzs9krSbiVu+EjE6RcQOi+Nbq0/ceVaWpquj'
    'UhThjPD+5eSWJz+OnyzvxIePoKE8f/lxcqum6rwmTXJyq2ZmCmCCpAhCR1YhdC92fVtmW7mqVkangv/eWQvnBQZUIv+vtuusTqwq'
    'v2XMkKqNdNRm1KwcrraJc0RIKNOVcQo5IM2NWRBdCGC3wvDQgT3BsbsEskIErHkS02Rlq084yRZsQF11oPed15KvomsPBmab5Lhk'
    '5muOKHqDuelkeI9974ZcObuLRnW2Zjs/jQ3HhQFkI3ir0dMK59aFZZyqBn/qQOdyhTbQj6Av26oJ2UzH9aGVGW3Rq61nnCPmcUxA'
    'DSbWs6nyKAEVnQApt96mWKBlBd2VjrFCk3Yus8u1iq0F5RQftPNSg8jQTsnIJAOz1m55P6t2UYx+e2HwMK6z5UMdAdNQR7Ajq4yg'
    'IoIcT5mtzWpR2Coxh5aepcxXKGATzpZIJ+iGKKJ1QMPSTGkLS8fLc419FNn6mD7QAtXbB5mfjumFKvb3Y01Qx3Rmazd79OgJFxnO'
    'm5t0nf0qE85KU4U37l1L573KDQcQ6auRG2dftULcbyLH6NC54aAiKDlVss4+SagO0gLVyxsP3hsMB1cQX+yy9SLhtDCsaBGtJ4a6'
    'mYNyPsLLxVJFfF+C6vOjLOzFCfMLl6JVmHi62aRE956T3aHTuHsh03n8Fo1iDR7mCdgkQIX4BwgJ/6AREv8qmyHV/7CSIOYxsrwu'
    'xBmFl6u8mCE6rOR7ih6LhqQ4m4SaaSU2u3WdASfHRJtQmy6wrhsXOioP5+TAho+OuEYE1jOD7bpD1xFuPha36pe59aMYdc0b/CUy'
    'WfIiExfvsgVLhA3u8GkotjbhEpw8arnx3F6wp+knbNXKFrAdMkRDP4xz4kf862O0Mn6YtQxvA72MIOD92UwDTACZ/PQ80PdidxoF'
    'acVKlnIYpERsOD1MilGF+myleGO29ipTqra+ysRDvOrMVXobEJ/wGjico7MVbxqKQzyTo7PHPCPmB1viww5jILpW0g/aDJ2tpWbX'
    '05B2wqGG856GNN/DTS96mtLM+5sqQ0peoCcGWrAL+D8mSLvwSkwSEH6BDG8ozpCY6IWhpGlA257YM0a7UqlTpoVK0VFGtxQUM9FR'
    'qG8asPzClPduXzTNNanakye3raOTS/M4pnmcxSvyMVT03g7TJlIf4waYjr/pCBgn6h4jzfeUMzmPmdB76jgUPGYCb1fsclllRqb5'
    'GHBYnXmYEnTgzMZ/ywM2ZmJQG5sgQzJaqqB8/zSwWA6OS8X58i2s07xQXrUw5AjZ9ALOKl0ZilecE/E4PwKVGZTOLZy8JauKxyH+'
    '5+BdrPKWe5FfAqNeCZ1glJxiOKny+zePVcZDm3+UZJEOcLDOFDia0kLwpzWQ7bZbo7ihbcJ01HevbUyPuP9N9Zj/4l0w8rB0vV2l'
    'yeMJjeUuyDxmp56G9c/xaNPu+9maMq4gi9iuMUuqRmTYdr/wcdmpCfxA/QmnP8z8p7oEhRfwUJR0MUZoDSmP3YOX7x5EaCPDGBR/'
    'BVSF87JA6njgYHqJiUapZqCDqxfLWDl0tNCJFHr0As3ZZo87Xg9hrM04e3v/jUGiPBO6VByY1BJqHOwJh9Ddx/IfPK7u4gecMc2U'
    'byV9umJolGvYIQo3hEWV7ezpMdkhJHR+cGdpYFX9d8Gq2kewaVrF+Fu50lVhuQz+dnFbylhW8xTQpBve/e0CGAmwF+AcNijBN1S5'
    'QLA7h0IOHdwxM/olY0di9gX24WO6tZl0FmVBGTow9rrcc5tdDmd+iQaS9d6sDJ0+9QL9lx3bhH9jtmuKlW5kcLOE5D3FaILERjOd'
    'O8N37ZrDuVodN5ILleC8qbV//eTx0z6t3duZ1ZWjvCty8K7yarxdMlds72Wt7tcQijq9NCXAiAMTcOO1QWdFE3rjlxQ6xNLkLneL'
    'z9XL4DfF49Dfc8aZyieusIYObMQzVJJ/EiKEEAOHCPHOg6LYycdUvVVOijonaeN6UHevElKvs0uMiKMABX9lgDEtJB7Wd5sNJ1aG'
    'YwmOiCkySGnkIJVcNtzHvBtEWLuwsZaGCVhiNuJFMcqKmUsna6Qcl5KMBZEd7zBHZx4+US8MAIhSIA+6fJe18ooT4Rxk8wh2N30W'
    'AK+79HbXvhLv6VsLZAPBW7AH0PgBAvsAKO+BOQszVR5i0l+h7V20hsNDmndNM+/rwNwPdV6JTZjhK0Ba5R3XUgpkYIqHvbB1xR6w'
    '+M5yqmp5MsRlpdYwvVQNfOZK0+Id3BJYcHRJlU42c7P3+CyWeKmmFh2papd6iGWlZFVBVOlSEkkwKQ3uC0ky52JoMwPtQjy4VTO+'
    'e6BpCRDk6gQIxnei+sQZRXEwpQha7S8Oog7ziT2k+Zu0M3WLolLHI9l1he6kSe0TfQ/BHoeKn62XNDpIG2/T/z1kaALb6mQV6K0D'
    'fGGqEDJrJ9OJAQ15GmKul3YrxtSBVh5NqowvcLzulq2/dX01wweyZq4uQp0agbi1Ywl3RdehBf793MYd6QiW4wF2mO9AVZMbyS4G'
    'HQjcXugw3pEdKQZ6W8PaYGmHG73r2swjOZYDeKEsoKyc1JRxu6G4hA4/m2rKGuptNdMkMfQSeKM1bII9URRSxfrtzd6lMg0sX5wP'
    'hUO2fpHT9RxnTpkokYqUbhJp4KcBfiLlmi0M6VYT1Ht1FMWo5zFel4JuIGQK6jnrHah1KiVFZWykhlhdoaOigOktXi75dDy1xrIh'
    'OS/SxIMZbKFVcT0Jsjyn25ttKRcZ+llPAv44kJ+xCbv/kpvoAoOEsdP4six224t9aMCMDJJYLeYGKgvsZ43ELmhoUb/Ns8VYZOyD'
    'AijiNPLWeb6Bs5Z9MbIm0RyNYOR7f7Fv20NRMePOYWB/011P4dUUSmcz94J/cDB77UHT/mcjA5F4zeb+e23OJFCM6lspquQviBAp'
    'qriTi310pxPJf6e+QaSYIkxkcnvNq8jJXTybwfVRJhz71SulQB9lneGLDPxYAl4E6wjkz7q+wMZ1trw/5P+zPpbQNmJgil8/OUwy'
    'ZP+ghg0/w6z7UNmlNwQS8Gtz93qW+O4PRrhtYYK++a40VwX++4YNv/GtCOvR0kbDpOtlVwZt/mQHp5iYls4mHNpp8ixnUc+lgUmX'
    'jPJz4thPgfepPvDn/IYwSj/3/HN23zVMMH1bbGcaEvQMqyu2WqLZRnc+ixeympfZhQyjqGWxdM/pfF2kDurYfLVQ64MPLVtYVzhv'
    'l8ttO3yL37PlDgu81xcSFhUGPPo6jnM4+2a6zoukhk/EXzAOzDG1KhZhb9vMMZkwI/6bvteBOP1PhDESD0WI3/fjT5D9J00n6jpm'
    '08IA/kRorwEN+WDcG/cwVANp8rMRceQ0Ye4Qcc6YJpCP7d6UcFfh7jyokfBifpYGwk2mhkoV/dMrQ62+xrFklePW+SCUzqQVodYG'
    'dUJHK1FSx8753stAizgVOmUcG6cqWFeJVgzFQv9LhZtOppXTTRq8dS84bH6LIjfSEOoYfhTfuDkw6u46e1unPsc7nt7QeJvaxg30'
    'nuhg74kJ+J54Ud+TUP2g6+CMVKKog5kBwuj7Qh3xll6s48T57bVW9UlhQG+ZxcIr5cXoTCwLxeY6kXYDckmXDG3JNLB9BWoY9Tiw'
    'QlCWm747Qe7Ecj91PaWv+s7k6E9Dw2QiQ0r3d+nC1d2r5WhWuTHgPjTDDFrfEHBzIV6DrnTt+Fhc+8ePa9+tidGsNJpmMmzV1Ppb'
    'XHuIZnZDSEYVzO/Ku9ziBr3Cy8EMZu9W3c6GDtEcpVj9BVWk45WpsMcGfEzIB78sMe6y8Q793uw7pfDIAtOeuFmcWqpYlyTs8DdR'
    'H4FNFqtGe/7AqDdE2+ytbu6GynGUTOvrdHOxSP0UUfDatYS3LeD2TcuSPRx8MbHd41xz0JuRGKX6Oi2oZjaexgbS8EJ54TQtnZcU'
    'bV/v7VAlQIUYO9jX2ab0x15tyTG5phg9/EFSJAT2EMRuMdOT95XYW0W1OucTfu00cBJEd7T3Pg/b39777GsvFO5HXO+Fpa+vjg/C'
    '9veFB+h2F+1PwHb3YPai0mzoPgGNhqG3QW3UpNbUtYELq3XcjHYkeMCWGLH5r+/fvBabXWWTZag+lTKv7ZEKKvwzpf84R/WmsZsC'
    'Kyq0ZoT6/qHLOojdtEwbXWk9XquDr/lsGjtkLfVdULlHK8oyu5kYtGqw9am62b4Upqo6ThM0xqULn/hOiOfcqcuZiqgaNip2KobG'
    'kKk+yVv1ffJRhPQlJudUgp4vh47WHixDc8Q02pP6O7z3pOhxlIGXAZPOB/o2LTT2AUfaJnjx5Gj0kyNOXXaOE/4zHLRUxIlVFk2h'
    'VRHNqx71zlawXH1ifzrtFXef6B+2qIlHHzPkomx8NZVnMn/ym4165L8cWWkJdc2K3uv12VhbLW4n+ofr1DWxP1uL75hEzWFtYn7G'
    'G1leylCDNxSYEttRhchquZbL2pKx48yjbUSqgL/UPDZfHVefxTHE436FPHITkAbT5y9n4he6TelpjLu3040o0JEmyXVSptddvpFW'
    'lfcUlKH13Wy4bR52onQwCh2pPpETtByQNVAGd29U+DJI6DV+g4/uo89fvj1xnaaUGVpPsBLG7m94hsLeV76eRKHQp8Oz2Vicisn3'
    'BpWYOXYozvAVmhjxMTZIwxsjMwvjwOTrZ63kbJQqsnHdrS9BMNV/EBzIjUI+Ew6X6Peh8ExintF1Ynh123GuAdik8TzsiOMioaDv'
    'zYd9F8YTR/fs6IVV0In6Ozx4BzRpqqft6p3Mp+dLMEvfnk0YjRrxJfY0v3Ht3/jdx9AjoyF/gO2M/IWbrRXJ4PWSGGFfaCtytsEj'
    '6v8hL3Kr9VcifKbi0kgSkrMFQE/Z5yglJ6bx+o6/TEEX1WZT9YLSve2i35hyc8m86C+4PdlzUfWK6awQO5Nb+DuOHy/vRHg6UVsM'
    'sDWBrRU18kZ2R+wdBwjD8ZodYiwX1DoQp1Fmgv2OUsUj89R3ogqsEeWMtnNw75k7E022LkF7AfWwZe+0zVgIDedbFOGtvIs+C0ad'
    'fOPgWVk5PlCKHc6foHMr6LTrx/XwTlb0DfYM2bL3sXQgZu+T6MpsQIH392Vx8A7iTur6dy/eJ6tVspTzwNdqho1meKi375yovUlQ'
    'WoidTtzoy0nnV9/9FA+TafOD7+7H3h0/YydIs/FNqlYksH96PVaR+qCOxG30G3j00fnzUA8NHNS/f/Hud6Nen95/H94tmgHn/iL0'
    '4D2kdKi+6SD6wguBxifUmlTUeLgYH0rOcU+ehSMj8zkX17QRbqpCTWfj1pfKluo2eEH+EHJHX5ZqXwx7sc5ekLMxa7ZivpvRzRzI'
    'ydvdRUupvybEFZgo3QrwJrK+Bhh76mxYm6gH+CcwwbfiqvKT9+DnNZdYgEuuw1pbEB2OvDU1h50GqUnXy8iddp4eXD5cCk4K6oxk'
    '8DHzHW3smnWukxmQV8o89q0Xn8Dh5MrGGY5951LUfWx7G7dtUo17rf58nxHCAzNgSWNFDHquLnaYwwnDjynDkJJDcSOWOzhfSZB5'
    'nD0P+Ug1bKQW4XA3+jyD8qhbyJqzb8etGO2DjgQq+vx1qvNCmShydhZA8n2EfFG8f/no+cuPEflruHg5OZNPTdy4FcYv8gq/NYRe'
    'sW4GOzYU+gGuHYmT7KqA/rzgg6Je3M8R98/WKj8hG/voRhP7ProLOjdki8o5A3uBP457FFsvvIra/q+q4ZBGj/VspNbNoCeZ3lgf'
    'YSV65+iTmjkqWxUWfuXO/Zu/PdrJ9BilhuJVa+8gYPxq6O7wV1D/NVKGpFM39qczI+MvYCI++LaOeuuCRQ3/UF/ARDN7FLaJusYU'
    'pETB3hoBE439hyL07CwR+rLmVulf6O8YYM4S/6tIHKOlwtMcPYBjs1RomvOeotGogH45JToUjQr1g/+tIi8IfuzcZPD3kEwQvVt0'
    'Z+9yafIkCTmIUoVHMkxDC8FQdOQCcEP3nXvfXqrBJ5dOLHfs+mx3M5cKezAqjBP/n3k5oAsvZaXjiGlsTp0el91HORXmy3ZkN5S8'
    'eSbZuPuUfAaVHyRO80BWYf90+tPSEBp948aEAISYsGtF5I+fI3fcTxWd4inm4Jl8E/V9z/ezZt5/rDzUDWwj55vXlgFkbQ7wW7c/'
    'E5W32zOz3RW3bvgPOV27bkSqdyTsPX+9z7ucxYHwr2oNEku7E5lR1HU92zZ9a2rbS/P1s59fJK+efXiN17rOZ0CXdeIbQ62qgKil'
    'QtONY2LUBlPtEFJKFPmhnt+tM+BYzwxrBKDIYpxTaDFhbls0GlFksKQ2W5vnOvXQ4X4N8qC28OzVqzfnMyNVFxqFeohbZ0RPLxBh'
    'taKUwRzXRlpHZJUFrxvrddS6xUNL0sCnNOOiei8hOKibgQJVJW4Eq48QM4ZycrUmNBeaKdMWfTTqw5sPz14FXQB7LT4HyB7anX2O'
    '/vOSr1hA9eS4nLDCWCG+dIDduc7YZRQZF6tnFvnR0cNUvspRUUx51TykzVrJkkAaHahkMkJ1d04Hvu4uG0UqY3xRJ8DIEoOKiYb7'
    'kR7EqMutuj4jhnZ0AhpSQ843M+FYd5AeHfE2uoEd86Q1hpeOStfWs++ofv9mffvuzQ8/vXrhKPfULd+NqLs3ooSxzhjF3ge4Z518'
    'Ufal8UzDVPLqU8qcJY8/Y8xuzZiP3SydAtc633hVHcEKU8QSQJ+ymtF1l57tUekwlGu3Fk3jhrdXw2vrkHBvymLy2WpbxwFjCCD3'
    'bbyG3DYHFBDb+GjMmBVmOtI5mXRPjxzSeehi3zFZeFjV3mvbJuzbyFnp9T7pd4JWPPiAH2GnFyGpr1TIHNTl6dZ1cNohs/X8u6bi'
    'fou3Ys4LiNh6esxKGRdQiVHfscXaDSXGmfdBJcbMTksV1mpwA66iobFBzDx09madcEYduurzcXpOt+TY1XOievxNaPRMeK7biidb'
    '9afRf4NsdQftkrP3CFgXpB4B24Daa/Gl0PRZUlYHOwvtukNilN1JboTJ2b+3EWpA0iQyHuOBdZPl6M9I352ib1dvZfpJ/PxRS2DO'
    'eWWEgt0UsG89JybMvngs1Kqh2olfRKvS+Pzd2pXa3L9T5fstYNBjSwN3Wo1F0EQ5KOLtKSi8Ok/qeNExRfKiuHcurmtFYyBQeRwS'
    'of1i/GkbuFP1W3OYoXgbHqzM1U7u68h2gtfCLrdBsm4T3O9jNb0E11hizDF4aInV2hKIm+sEtqRdVif4sb2eVirp2R2xnL3TsIvs'
    'kBQMPfUgUwGKjZeuBcO2Y2ZDTZjdtBtqVvcMtBhis+j9bzwV+4QDF3yx49cXXC8P8h4Z4s7M/P7SW9QBwttDk44SZwc127Y295lS'
    'Bp06XcusyzoW2wQNz4scTvJ2baeNzxhvpy3D0bT789kGN93FjK/usg6bSUc575XuGizHu8sc1B+uYZegp563ED11XGT3VFFr1S71'
    'k1Y3UnfZBf3/K/K/vyLuvTt9ukKxM+vwEMVVUdbKJTCctm2SM7T1oXuY+vxDWWxd7/njVM+P+HlZdcNWfabyR27I1VXo+Onj2cVy'
    'ZUfb1nUdn/yOuu6yNXq3nvO9Y/jtWh73He1g3XR17VTfqOV6jX4si1qOG07fYiRuHQTcdRQ7c77rb20BPdDH4Up6DmRpOSaB3quf'
    'jgoR4q/UpuWlOaCTLlNe8jfHn5WXu43M67f4pBPQbOMUQ5lUURiMRlb46YOKk8OrXV0JSG0TOrIVOaKM0KMGrwP54nfCmfCHYr4q'
    'srnEs7B6ETiWgb6+Ssro+RmD8yXZUQ1oT49UxMWxjdCZv86Wx1ZHr/aj62aX69EiOxp+5YU5Wqy6IWr7IWebbVlcyZ4UjZwXseWg'
    'bFyTezFiPG5HGONiV54uPynz4yQ4f/9v+J0bqqzzHmiHaMpXhT4ROrmO/fKTifJoDQuznq+2I/bT1KSqvrmsATiNv9Hjk4+nWKbo'
    '3qX9y42zp3Ht1N7TE+M63Ts+Dg78HzbW2iV2ytOm58zeHZThS8XeUNKxlTSzDhfajx4aRodHg/ruSJT3TY30fnehvi3ErkfLfedS'
    'Krx7qcEOj2mc0RvTtBni9Fy1FUW5tFAmZ8Sz9RDFOSsjtp22bhcZV9A2IBxn1UHg3dXxFnSExpzRvIcuzr7Vp6x2a4oaoeY9jR/j'
    'VQFPWt5sgcTzGnNUYxoNFTva1zXGnCAD6YOqu2MVSdTbK4WDEPP4vH7J06KRb59DWVQK2ah3SCAMx6NspBS4ni34xOxBHgy4gHGB'
    '26B9li6xgDZCx3Ouf2ztFznKixHeFcFplFynoPsaNbkaSCOw8yWvSuNMiUEh7IzJ+WDZhat7LOvQMRoBnEq+kJflqC4cddNsCu8z'
    'aBwloEWeKsIvbBmHKecemYD9aakcnDGn2wNymXkg+L4c3V3gmfKok68FZ4BzfbOG6IDBw8R+bqT+aVFQ2AidHkiupdWIQ2GcKXQh'
    'tw03sBOKSNMfQ1TxPOxOgYtOI3Fudx5CZzKgWDjDIw5CDgCr+7LuRfeSgmxjV29SCUI2wIG1EoUFeIp2a5EjmI3IdsNFsEbcihmh'
    'CDUq6nMt5tIuV2PjMO5W8fzHjV+zW8Nzc/aCRrmW92o4aGSk4Tqt9DQ2DI/K8dEp1NFoXKZD0noCrbhWI/jK9RQ2PfFvF0Q/lEeB'
    '2hPP40WxcF0/sGXgxurooB5exq7IHh3RY2p4YT3NCB5bzY/r6QxUpLr3RitipYMhi9xNK27RiQykGk54oF2iLr9gXqiOEtuu4YTO'
    'TRovfcd03xedGxzyUe+LS1VD9ZS2fdypetPRfYBfTOMcywl9lCtJkAUkiYpYY34w+B9s1ohcJbcAAA=='
)

FLEX_HEAT_COLUMNS = [
    "System", "zone", "unit_name", "year", "cap_mw", "max_cap",
    "max_cap_period", "share2020", "storage_capacity_relation", "var_cost",
    "life_time", "decom_start_existing_cap", "decom_start_new",
    "final_life_cap", "max_gen_aval_TWh", "Tech_type", "Note",
]
FLEX_DH_COLUMNS = [
    "System", "zone", "unit_name", "year", "cap_mw", "max_cap",
    "max_cap_period", "share2020", "var_cost", "life_time",
    "decom_start_existing_cap", "decom_start_new", "final_life_cap",
    "max_gen_aval_TWh", "Tech_type",
]
THERMAL_COLUMNS = [
    "System", "zone", "unit_name", "fuel_type", "efficiency", "year",
    "cap_mw", "max_cap", "max_cap_period", "share2020", "heat_storage_cap",
    "CO2Intensity", "decom_start_existing_cap", "life_time",
    "decom_start_new", "final_life_cap", "max_gen_aval_TWh", "Tech_type",
]
THERMAL_DH_COLUMNS = [
    "System", "zone", "unit_name", "fuel_type", "efficiency", "year",
    "cap_mw", "max_cap", "max_cap_period", "share2020", "CO2Intensity",
    "decom_start_existing_cap", "life_time", "decom_start_new",
    "final_life_cap", "max_gen_aval_TWh", "Tech_type",
]
SOLAR_INDV_COLUMNS = [
    "unit_name", "fuel_type", "efficiency", "year", "cap_mw", "max_cap",
    "max_cap_period", "decom_start_existing_cap", "life_time",
    "decom_start_new", "final_life_cap", "max_gen_aval_TWh", "zone",
    "System", "solar_curve",
]
SOLAR_DH_COLUMNS = [
    "unit_name", "fuel_type", "efficiency", "year", "cap_mw", "max_cap",
    "max_cap_period", "decom_start_existing_cap", "life_time",
    "decom_start_new", "final_life_cap", "zone", "System", "solar_curve",
]

FLEX_INDV = {
    "Air_to_water_HP": ("heat_pump", 100000, 10000, 2, 1, 100.0),
    "Ground_to_water_HP": (None, 0, 10000, 2, 1, 0.15),
    "Electric_heater": ("electric_heater", 100000, 10000, 2, 1, 10.0),
    "Water_to_water_HP": (None, 100000, 10000, 2, 1, 0.01),
}
FLEX_DH = {
    "Air_to_water_HP_DH": (100000, 10000, 0.3),
    "Ground_to_water_HP_DH": (0, 10000, 10.0),
    "Electric_heater_DH": (100000, 10000, 10.0),
    "Water_to_water_HP_DH": (100000, 10000, 10.0),
}
THERMAL = {
    "Gas": ("gas", "Gas", .99, .20, 0, 0),
    "Biomass": ("biomass", "Biomass", .83, 0, 200, 50),
    "fuel_oil": ("oil", "fuel_oil", .99, .27, 0, 0),
    "Coal": ("coal", "Coal", .99, .38, 0, 0),
    "Geothermal": (None, "Geothermal", 1.0, 0, 0, 0),
}
THERMAL_DH = {
    "Gas_DH": ("Gas", .99, .20),
    "Biomass_DH": ("Biomass", .83, 0),
    "fuel_oil_DH": ("fuel_oil", .99, .27),
    "Coal_DH": ("Coal", .99, .38),
    "Geothermal_DH": ("Geothermal", 1.0, 0),
}


def parse_countries(raw: str) -> list[str]:
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def download_file(url: str, target: Path, refresh: bool = False) -> Path:
    if target.exists() and target.stat().st_size > 0 and not refresh:
        print(f"Using cached: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    if refresh:
        partial.unlink(missing_ok=True)
    print(f"Downloading {url}\n       -> {target}")
    last_error: Exception | None = None
    for attempt in range(1, 6):
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "heating-input-generator/1.0"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                resumed = existing > 0 and getattr(response, "status", None) == 206
                mode = "ab" if resumed else "wb"
                with partial.open(mode) as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            if not partial.exists() or partial.stat().st_size == 0:
                raise RuntimeError(f"Downloaded file is empty: {url}")
            partial.replace(target)
            return target
        except Exception as exc:
            last_error = exc
            if attempt == 5:
                break
            delay = min(30, 2 ** attempt)
            print(
                f"Download attempt {attempt}/5 failed ({exc}); "
                f"retrying in {delay}s..."
            )
            time.sleep(delay)
    raise RuntimeError(f"Download failed after 5 attempts: {url} ({last_error})")


def safe_extract_zip(archive: Path, target: Path) -> None:
    marker = target / ".extracted"
    if marker.exists():
        return
    target.mkdir(parents=True, exist_ok=True)
    root = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            destination = (target / member.filename).resolve()
            if root not in destination.parents and destination != root:
                raise ValueError(f"Unsafe ZIP member: {member.filename}")
        bundle.extractall(target)
    marker.touch()


def materialize_calculator(cache: Path) -> Path:
    path = cache / "_embedded_nuts3_heat_calculator.py"
    source = gzip.decompress(base64.b64decode(RAW_CALCULATOR_GZ_B64))
    if not path.exists() or path.read_bytes() != source:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
    return path


def download_era5_land(target: Path, year: int) -> Path:
    if target.exists() and target.stat().st_size > 0:
        print(f"Using cached: {target}")
        return target
    try:
        import cdsapi
    except ImportError as exc:
        raise RuntimeError(
            "ERA5-Land automatic download needs the 'cdsapi' package. Install it "
            "and configure ~/.cdsapirc, or supply --era5 PATH."
        ) from exc
    target.parent.mkdir(parents=True, exist_ok=True)
    print("Requesting hourly ERA5-Land 2 m temperature from the Copernicus CDS.")
    print("This is the largest download and may take considerable time.")
    request = {
        "variable": ["2m_temperature"],
        "year": [str(year)],
        "month": [f"{month:02d}" for month in range(1, 13)],
        "day": [f"{day:02d}" for day in range(1, 32)],
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": [72, -25, 34, 45],
    }
    cdsapi.Client().retrieve("reanalysis-era5-land", request, str(target))
    return target


def find_idees_workbook(root: Path, country: str, sector: str) -> Path:
    aliases = {"GR": "EL"}
    code = aliases.get(country, country)
    names = [
        f"JRC-IDEES-2021_{sector}_{code}.xlsx",
        f"JRC-IDEES-2021_{sector}_{country}.xlsx",
    ]
    for name in names:
        matches = list(root.rglob(name))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No JRC-IDEES {sector} workbook found for {country}")


def prepare_sources(args: argparse.Namespace) -> dict[str, Path]:
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    nuts = args.nuts3_geojson or download_file(
        NUTS_URL, data / "NUTS_RG_01M_2021_4326_LEVL_3.geojson", args.refresh_sources
    )
    population = args.population_tif
    if population is None:
        if not args.accept_population_terms:
            raise RuntimeError(
                "Population-grid download requires acceptance of Eurostat/GISCO "
                "population-grid terms. Review them, then rerun with "
                "--accept-population-terms; or pass --population-tif PATH."
            )
        population = download_file(
            POP_URL, data / "ESTAT_OBS-VALUE-T_2021_V2.tiff", args.refresh_sources
        )
    eigl = args.eigl_dir or data / "EIGL"
    if args.eigl_dir is None:
        for filename in EIGL_FILES:
            download_file(
                f"{EIGL_BASE_URL}/{filename}", eigl / filename, args.refresh_sources
            )
    hotmaps = args.hotmaps_dh_tif or download_file(
        HOTMAPS_URL, data / "heat_tot_curr_density.tif", args.refresh_sources
    )
    idees_root = args.idees_root
    if idees_root is None:
        idees_zip = download_file(
            IDEES_URL, data / "JRC-IDEES-2021.zip", args.refresh_sources
        )
        idees_root = data / "JRC-IDEES-2021"
        if args.refresh_sources:
            (idees_root / ".extracted").unlink(missing_ok=True)
        safe_extract_zip(idees_zip, idees_root)
    if args.era5 is not None:
        era5 = args.era5
    elif args.temperature_source == "open-meteo":
        era5 = data / "open_meteo_era5_land"
        era5.mkdir(parents=True, exist_ok=True)
        print(f"ERA5-Land sampled-point series will be cached under: {era5}")
    else:
        era5 = download_era5_land(
            data / f"era5_land_t2m_{args.source_year}.nc", args.source_year
        )
    powerplants = args.powerplants_csv
    if powerplants is None:
        shared = SCRIPT_DIR.parent / "power/data/powerplants.csv"
        powerplants = shared if shared.is_file() else data / "powerplants.csv"
        if not Path(powerplants).is_file() or args.refresh_sources:
            download_file("https://raw.githubusercontent.com/PyPSA/powerplantmatching/master/powerplants.csv",
                          Path(powerplants), args.refresh_sources)
    if not Path(powerplants).is_file():
        raise FileNotFoundError(f"CHP location source is missing: {powerplants}")
    args.powerplants_csv = Path(powerplants)
    return {
        "nuts": Path(nuts), "population": Path(population), "eigl": Path(eigl),
        "hotmaps": Path(hotmaps), "idees": Path(idees_root), "era5": Path(era5),
        "powerplants": Path(powerplants),
        "calculator": materialize_calculator(data),
    }


def generate_raw_outputs(args: argparse.Namespace, sources: dict[str, Path]) -> Path:
    raw_root = args.raw_output_root.resolve()
    raw_root.mkdir(parents=True, exist_ok=True)
    for country in args.countries:
        output = raw_root / (
            f"{country}_{args.source_year}_popHDD_fuelEIGL_hotmapsDH_v4"
        )
        expected = output / f"hourly_nuts3_{country}_{args.source_year}.csv"
        from heating.method_provenance import raw_fingerprint, raw_cache_matches, write_raw_manifest
        identity = raw_fingerprint(args, sources, country)
        if expected.exists() and not args.rebuild_raw and raw_cache_matches(output, identity):
            print(f"Using cached NUTS3 calculation: {output}")
            continue
        (output / "paper_generation.json").unlink(missing_ok=True)
        command = [
            sys.executable, str(SCRIPT_DIR / "paper_calculator.py"),
            "--calculator", str(sources["calculator"]),
            "--weather-points", str(args.weather_points), "--weather-seed", str(args.weather_seed),
            "--country", country, "--year", str(args.source_year),
            "--idees-unit", "ktoe",
            "--idees-res", str(find_idees_workbook(sources["idees"], country, "Residential")),
            "--idees-ter", str(find_idees_workbook(sources["idees"], country, "Tertiary")),
            "--nuts3-geojson", str(sources["nuts"]),
            "--pop-tif", str(sources["population"]),
            "--era5", str(sources["era5"]),
            "--eigl-dir", str(sources["eigl"]),
            "--hotmaps-dh-tif", str(sources["hotmaps"]),
            "--outdir", str(output),
            "--dh-chp-lambda", str(args.dh_chp_lambda),
        ]
        if args.powerplants_csv:
            command.extend(["--powerplants-csv", str(args.powerplants_csv)])
        print(f"Calculating hourly NUTS3 heating demand for {country}...")
        subprocess.run(command, check=True)
        write_raw_manifest(output, identity)
    return raw_root


def locate_country_dir(root: Path, country: str, year: int) -> Path:
    patterns = [
        f"{country}_{year}_popHDD_fuelEIGL_hotmapsDH_v4",
        f"{country}_{year}_popHDD_fuelEIGL_hotmapsDH_v4*",
        f"{country}_{year}_popHDD_fuelEIGL_hotmapsDH_v3*",
    ]
    for pattern in patterns:
        matches = sorted(path for path in root.glob(pattern) if path.is_dir())
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No heating result directory for {country} under {root}")


def load_zone_map(path: Path | None) -> pd.DataFrame | None:
    if path is None:
        return None
    data = pd.read_csv(path)
    aliases = {
        "System": "country", "system": "country", "country": "country",
        "zone_old": "nuts3_id", "nuts3": "nuts3_id", "NUTS_ID": "nuts3_id",
        "zone_new": "zone", "zone": "zone",
    }
    data = data.rename(columns={col: aliases[col] for col in data if col in aliases})
    required = {"country", "nuts3_id", "zone"}
    if not required.issubset(data):
        raise ValueError(f"Zone map requires {sorted(required)}")
    return data[list(required)].drop_duplicates()


def attach_zones(data: pd.DataFrame, zone_map: pd.DataFrame | None) -> pd.DataFrame:
    out = data.copy()
    out["country"] = out["country"].astype(str).str.upper()
    out["nuts3_id"] = out["nuts3_id"].astype(str)
    if zone_map is None:
        out["zone"] = out["nuts3_id"]
        return out
    result = out.merge(zone_map, on=["country", "nuts3_id"], how="left")
    result["zone"] = result["zone"].fillna(result["nuts3_id"])
    return result


def read_country_outputs(
    input_root: Path, country: str, source_year: int, zone_map: pd.DataFrame | None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    folder = locate_country_dir(input_root, country, source_year)
    hourly = pd.read_csv(folder / f"hourly_nuts3_{country}_{source_year}.csv")
    capacity = pd.read_csv(folder / f"capacity_template_{country}_{source_year}.csv")
    return attach_zones(hourly, zone_map), attach_zones(capacity, zone_map)


def aggregate_hourly(hourly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hourly["utc_hour"] = pd.to_numeric(hourly["utc_hour"], errors="raise").astype(int)
    hourly["mwh"] = pd.to_numeric(hourly["mwh"], errors="coerce").fillna(0.0)
    district = hourly["fuel"].astype(str).eq("district_heating")
    grouped = (
        hourly.assign(kind=np.where(district, "DH", "indv"))
        .groupby(["country", "zone", "kind", "utc_hour"], as_index=False)["mwh"].sum()
    )
    def wide(kind: str) -> pd.DataFrame:
        selected = grouped[grouped["kind"].eq(kind)]
        table = selected.pivot_table(
            index="utc_hour", columns=["country", "zone"], values="mwh",
            aggfunc="sum", fill_value=0,
        ).sort_index()
        table.columns = [f"{country}::{zone}" for country, zone in table.columns]
        table.insert(0, "period", np.arange(1, len(table) + 1))
        return table.reset_index(drop=True)
    return wide("indv"), wide("DH")


def aggregate_capacity(capacity: pd.DataFrame) -> pd.DataFrame:
    cap = capacity[capacity["fuel"].astype(str).str.upper().ne("TOTAL")].copy()
    for col in ("annual_mwh", "cap_mw"):
        cap[col] = pd.to_numeric(cap[col], errors="coerce").fillna(0.0)
    result = cap.groupby(["country", "zone", "fuel"], as_index=False).agg(
        annual_mwh=("annual_mwh", "sum"), cap_mw=("cap_mw", "sum")
    )
    non_dh = result["fuel"].ne("district_heating")
    totals = (
        result[non_dh].groupby(["country", "zone"])["annual_mwh"].sum()
        .rename("indv_total").reset_index()
    )
    result = result.merge(totals, on=["country", "zone"], how="left")
    result["share"] = np.where(
        non_dh & result["indv_total"].gt(0),
        result["annual_mwh"] / result["indv_total"], 0.0,
    )
    return result


def block_values(capacity: pd.DataFrame, system: str, zone: str) -> dict[str, dict[str, float]]:
    block = capacity[
        capacity["country"].eq(system) & capacity["zone"].astype(str).eq(str(zone))
    ]
    return {
        str(row.fuel): {
            "cap": float(row.cap_mw), "share": float(row.share),
            "annual": float(row.annual_mwh),
        }
        for row in block.itertuples(index=False)
    }


def standard_lifetime() -> dict[str, object]:
    return {
        "life_time": 15, "decom_start_existing_cap": 8,
        "decom_start_new": 10, "final_life_cap": .1,
    }


def build_sheets(capacity: pd.DataFrame, model_year: int) -> dict[str, pd.DataFrame]:
    flex_rows, flex_dh_rows = [], []
    thermal_rows, thermal_dh_rows = [], []
    solar_rows, solar_dh_rows = [], []
    zones = capacity[["country", "zone"]].drop_duplicates()
    for system, zone in zones.itertuples(index=False):
        values = block_values(capacity, system, zone)
        for unit, (fuel, maximum, period_max, storage, var_cost, max_twh) in FLEX_INDV.items():
            source = values.get(fuel or "", {})
            flex_rows.append({
                "System": system, "zone": zone, "unit_name": unit, "year": model_year,
                "cap_mw": source.get("cap", 0.0), "max_cap": maximum,
                "max_cap_period": period_max, "share2020": source.get("share", 0.0),
                "storage_capacity_relation": storage, "var_cost": var_cost,
                **standard_lifetime(), "max_gen_aval_TWh": max_twh,
                "Tech_type": "Heat pumps", "Note": None,
            })
        for unit, (maximum, period_max, max_twh) in FLEX_DH.items():
            flex_dh_rows.append({
                "System": system, "zone": zone, "unit_name": unit, "year": model_year,
                "cap_mw": 0.0, "max_cap": maximum, "max_cap_period": period_max,
                "share2020": 0.0, "var_cost": 1, **standard_lifetime(),
                "max_gen_aval_TWh": max_twh, "Tech_type": "Heat pumps",
            })
        for unit, (source_fuel, fuel_type, efficiency, co2, maximum, period_max) in THERMAL.items():
            source = values.get(source_fuel or "", {})
            thermal_rows.append({
                "System": system, "zone": zone, "unit_name": unit,
                "fuel_type": fuel_type, "efficiency": efficiency, "year": model_year,
                "cap_mw": source.get("cap", 0.0), "max_cap": maximum,
                "max_cap_period": period_max, "share2020": source.get("share", 0.0),
                "heat_storage_cap": 0, "CO2Intensity": co2,
                **standard_lifetime(),
                "max_gen_aval_TWh": source.get("annual", 0.0) / 1e6,
                "Tech_type": "boiler",
            })
        district = values.get("district_heating", {})
        for unit, (fuel_type, efficiency, co2) in THERMAL_DH.items():
            is_gas = unit == "Gas_DH"
            thermal_dh_rows.append({
                "System": system, "zone": zone, "unit_name": unit,
                "fuel_type": fuel_type, "efficiency": efficiency, "year": model_year,
                "cap_mw": district.get("cap", 0.0) if is_gas else 0.0,
                "max_cap": 0, "max_cap_period": 0,
                "share2020": 1.0 if is_gas and district.get("annual", 0) > 0 else 0.0,
                "CO2Intensity": co2, **standard_lifetime(),
                "max_gen_aval_TWh": district.get("annual", 0.0) / 1e6 if is_gas else 0.0,
                "Tech_type": "boiler_DH",
            })
        indv_twh = sum(
            item["annual"] for fuel, item in values.items() if fuel != "district_heating"
        ) / 1e6
        solar_rows.append({
            "unit_name": "Solar", "fuel_type": "solar", "efficiency": 1,
            "year": model_year, "cap_mw": 0, "max_cap": 10000,
            "max_cap_period": 0, "decom_start_existing_cap": 30,
            "life_time": 50, "decom_start_new": 40, "final_life_cap": .1,
            "max_gen_aval_TWh": indv_twh, "zone": zone, "System": system,
            "solar_curve": "continental",
        })
        solar_dh_rows.append({
            "unit_name": "Solar_DH", "fuel_type": "solar", "efficiency": 1,
            "year": model_year, "cap_mw": 0, "max_cap": 1000,
            "max_cap_period": 0, "decom_start_existing_cap": 30,
            "life_time": 50, "decom_start_new": 40, "final_life_cap": .1,
            "zone": zone, "System": system, "solar_curve": "continental",
        })
    return {
        "flex_tech_heat": pd.DataFrame(flex_rows, columns=FLEX_HEAT_COLUMNS),
        "flex_tech_DH": pd.DataFrame(flex_dh_rows, columns=FLEX_DH_COLUMNS),
        "thermal_tech": pd.DataFrame(thermal_rows, columns=THERMAL_COLUMNS),
        "thermal_tech_DH": pd.DataFrame(thermal_dh_rows, columns=THERMAL_DH_COLUMNS),
        "solar_indv": pd.DataFrame(solar_rows, columns=SOLAR_INDV_COLUMNS),
        "solar_DH": pd.DataFrame(solar_dh_rows, columns=SOLAR_DH_COLUMNS),
    }


def friendly_curve_columns(curve: pd.DataFrame, systems: int) -> pd.DataFrame:
    out = curve.copy()
    renamed = {}
    for col in out.columns:
        if col == "period":
            continue
        system, zone = col.split("::", 1)
        renamed[col] = zone
    out = out.rename(columns=renamed)
    if out.columns.duplicated().any():
        raise ValueError("Heating model zones must be globally unique across systems")
    return out


def validate(
    sheets: dict[str, pd.DataFrame], individual: pd.DataFrame, district: pd.DataFrame
) -> None:
    expected = {
        "flex_tech_heat": 4, "flex_tech_DH": 4,
        "thermal_tech": 5, "thermal_tech_DH": 5,
        "solar_indv": 1, "solar_DH": 1,
    }
    zones = sheets["solar_indv"][["System", "zone"]].drop_duplicates().shape[0]
    for name, rows_per_zone in expected.items():
        if len(sheets[name]) != zones * rows_per_zone:
            raise ValueError(f"{name}: invalid row count")
    if len(individual) not in (8760, 8784) or len(district) != len(individual):
        raise ValueError("Heating demand curves must contain one complete year")
    print(f"Validated {zones} heating zones and {len(individual)} hourly periods.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download raw heating resources, calculate NUTS3 demand, and generate "
            "model-ready H2RES sheets and hourly curves."
        )
    )
    parser.add_argument("--countries", type=parse_countries, default=parse_countries("HR"))
    parser.add_argument("--source-year", type=int, default=2021)
    parser.add_argument("--efuels", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--model-year", type=int, default=YEAR)
    parser.add_argument("--zone-map", type=Path)
    parser.add_argument("--out-root", type=Path, default=SCRIPT_DIR / "outputs_heating")
    parser.add_argument("--data-dir", type=Path, default=SCRIPT_DIR / "heating_data")
    parser.add_argument(
        "--raw-output-root", type=Path,
        default=SCRIPT_DIR / "generated_nuts3_heating",
    )
    parser.add_argument(
        "--skip-raw-generation", action="store_true",
        help="Only aggregate existing raw outputs supplied with --input-root.",
    )
    parser.add_argument("--input-root", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--rebuild-raw", action="store_true")
    parser.add_argument(
        "--accept-population-terms", action="store_true",
        help="Confirm acceptance of the Eurostat/GISCO population-grid terms.",
    )
    parser.add_argument("--nuts3-geojson", type=Path)
    parser.add_argument("--population-tif", type=Path)
    parser.add_argument("--era5", type=Path, help="Existing ERA5/ERA5-Land NetCDF.")
    parser.add_argument(
        "--temperature-source", choices=["open-meteo", "cds-netcdf"],
        default="open-meteo",
        help=(
            "Temperature source when --era5 is not supplied: cached Open-Meteo "
            "ERA5-Land sampled-point series (default) or a CDS NetCDF download."
        ),
    )
    parser.add_argument("--eigl-dir", type=Path)
    parser.add_argument("--hotmaps-dh-tif", type=Path)
    parser.add_argument("--idees-root", type=Path)
    parser.add_argument("--powerplants-csv", type=Path)
    parser.add_argument("--weather-points", type=int, choices=[8], default=8,
                        help="Population-weighted random grid samples per NUTS3 region (paper method: 8)")
    parser.add_argument("--weather-seed", type=int, default=0,
                        help="Reproducible random sampling seed")
    parser.add_argument(
        "--dh-chp-lambda", type=float, default=0.9,
        help="DH spatial-weight blend: 0=Hotmaps only, 1=CHP only (default: 0.9).",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        input_root = args.input_root
        if not args.skip_raw_generation:
            sources = prepare_sources(args)
            input_root = generate_raw_outputs(args, sources)
        zone_map = load_zone_map(args.zone_map)
        hourly_frames, capacity_frames = [], []
        for country in args.countries:
            hourly, capacity = read_country_outputs(
                input_root, country, args.source_year, zone_map
            )
            hourly_frames.append(hourly)
            capacity_frames.append(capacity)
        hourly = pd.concat(hourly_frames, ignore_index=True)
        capacity = aggregate_capacity(pd.concat(capacity_frames, ignore_index=True))
        individual, district = aggregate_hourly(hourly)
        systems = len(args.countries)
        individual = friendly_curve_columns(individual, systems)
        district = friendly_curve_columns(district, systems)
        sheets = build_sheets(capacity, args.model_year)
        if not args.efuels:
            for name in ("thermal_tech", "thermal_tech_DH"):
                sheets[name]["fuel_type"] = sheets[name]["fuel_type"].replace({"fuel_oil": "Oil"})
                sheets[name]["unit_name"] = sheets[name]["unit_name"].replace({"fuel_oil": "Oil", "fuel_oil_DH": "Oil_DH"})
        validate(sheets, individual, district)

        args.out_root.mkdir(parents=True, exist_ok=True)
        system_tag = "_".join(args.countries)
        individual_path = (
            args.out_root / f"heat_demand_{system_tag}_{args.model_year}_2050_sdewes_indv.csv"
        )
        district_path = (
            args.out_root / f"heat_demand_{system_tag}_{args.model_year}_2050_sdewes_DH.csv"
        )
        individual.to_csv(individual_path, index=False)
        district.to_csv(district_path, index=False)
        individual.to_csv(args.out_root / "heating_individual.csv", index=False)
        district.to_csv(args.out_root / "heating_district.csv", index=False)
        # The raw IDEES heating tables contain final energy. The electric
        # portion is the baseline electricity to remove from total grid load.
        electric = hourly.loc[hourly.fuel.isin(["electric_heater", "heat_pump"])].copy()
        if electric.empty:
            electricity = individual.copy()
            electricity.loc[:, electricity.columns != "period"] = 0.0
        else:
            electricity, _ = aggregate_hourly(electric)
            electricity = friendly_curve_columns(electricity, systems)
            electricity = individual[["period"]].merge(electricity, on="period", validate="one_to_one")
            for zone in individual.columns:
                if zone not in electricity:
                    electricity[zone] = 0.0
        electricity.to_csv(args.out_root / "heating_electricity.csv", index=False)
        for name, frame in sheets.items():
            frame.to_csv(args.out_root / f"{name}.csv", index=False)
        workbook = args.out_root / "heating_inputs.xlsx"
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            for name, frame in sheets.items():
                frame.to_excel(writer, sheet_name=name, index=False)
        print(f"Wrote heating workbook: {workbook}")
        print(f"Wrote individual heating curve: {individual_path}")
        print(f"Wrote district-heating curve: {district_path}")
        from sector_method_provenance import write_heating
        write_heating(args, input_root)
        return 0
    except (
        FileNotFoundError, ValueError, KeyError, RuntimeError,
        subprocess.CalledProcessError, urllib.error.URLError, zipfile.BadZipFile,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
