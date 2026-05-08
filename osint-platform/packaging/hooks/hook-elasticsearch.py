# PyInstaller hook for elasticsearch[async]
# Belt-and-braces: collect_all() in osint.spec usually catches everything,
# but the elasticsearch client uses runtime imports for transports.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    collect_submodules("elasticsearch")
    + collect_submodules("elastic_transport")
    + [
        "elasticsearch._async",
        "elasticsearch._async.client",
        "elasticsearch._async.helpers",
        "elasticsearch.helpers",
        "elastic_transport._async_transport",
        "elastic_transport._node._http_aiohttp",
        "elastic_transport._node._http_urllib3",
    ]
)

datas = collect_data_files("elasticsearch") + collect_data_files("elastic_transport")
