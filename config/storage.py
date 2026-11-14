"""Static file storage for production."""
from whitenoise.storage import CompressedManifestStaticFilesStorage


class StaticStorage(CompressedManifestStaticFilesStorage):
    """
    Compressed, cache-busting static files (WhiteNoise) that don't crash on a path missing from the
    manifest. The admin theme (Jazzmin 3) asks for the folder `vendor/bootswatch` in its theme switcher;
    strict mode turned that into a server error on every admin page. Real files still get hashed names.
    """

    manifest_strict = False
