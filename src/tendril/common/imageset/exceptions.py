

from tendril.common.exceptions import HTTPCodedException
from tendril.common.interests.exceptions import InterestActionException
from tendril.common.interests.exceptions import InterestTypeUnsupported


class ContentNotReady(InterestActionException):
    status_code = 406

    def __init__(self, *args, **kwargs):
        super(ContentNotReady, self).__init__(*args, **kwargs)

    def __str__(self):
        return f"The interest {self.interest_id}, {self.interest_name} does not have " \
               f"an associated imageset containter.'{self.action}' cannot be performed."


class FileTypeUnsupported(InterestActionException):
    status_code = 406

    def __init__(self, extension, allowed, *args, **kwargs):
        super(FileTypeUnsupported, self).__init__(*args, **kwargs)
        self.extension = extension
        self.allowed = allowed

    def __str__(self):
        return f"Imageset content upload to interest {self.interest_id}, {self.interest_name} " \
               f"failed. Provided file has extension '{self.extension}' which is unsupported. " \
               f"Supported extensions are `{self.allowed}`."
