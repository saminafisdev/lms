from whitenoise.storage import CompressedManifestStaticFilesStorage


class RelaxedManifestStaticFilesStorage(CompressedManifestStaticFilesStorage):
    """
    WhiteNoise's CompressedManifestStaticFilesStorage with manifest_strict=False.
    Prevents collectstatic from failing when a JS/CSS file references a sourcemap
    (.map) that isn't included in the package (e.g. Jazzmin's Bootstrap).
    """
    manifest_strict = False
