import datetime
import re

TIMEDELTA_REGEX = r'^(?!$)(?:(?P<weeks>\d+)w)?(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)[hH])?(?:(?P<minutes>\d+)[mM])?(?:(?P<seconds>\d+)[sS])?(?:(?P<milliseconds>\d+)m)?(?:(?P<microseconds>\d+)u)?$'


def parse_timedelta(argument: str) -> datetime.timedelta:
    match = re.match(TIMEDELTA_REGEX, argument)
    if match is None:
        return

    groups = {k: int(v) for k, v in match.groupdict(default='0').items()}
    return datetime.timedelta(**groups)


def format_timedelta(timedelta=None, **kwargs):
    if timedelta is None:
        timedelta = datetime.timedelta(**kwargs)

    return re.sub(r'^(?:(?:0:)|(\d+:))(\d+:\d+)(?:\.\d+)?$', '\g<1>\g<2>',
                  str(timedelta))
