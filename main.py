from starlite import CompressionConfig, CORSConfig, Starlite

from chat import chat, chat_streaming, chat_streaming_reformed

app = Starlite(
    [chat, chat_streaming, chat_streaming_reformed],
    compression_config=CompressionConfig(backend="brotli", brotli_gzip_fallback=True),
    cors_config=CORSConfig(allow_origins=["*.muspimerol.site", "localhost"])
)
