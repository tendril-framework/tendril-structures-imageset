

from tendril.apiserver.templates.imageset import InterestImageSetRouterGenerator


class ImageSetLibraryMixin(object):
    _additional_api_generators = [InterestImageSetRouterGenerator]

    def __init__(self, *args, **kwargs):
        super(ImageSetLibraryMixin, self).__init__(*args, **kwargs)
