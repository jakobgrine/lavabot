from datetime import datetime
import wavelink


class Track(wavelink.Track):
    """Wavelink Track object with a requester attribute."""

    __slots__ = ('requester', 'requested_at')

    def __init__(self, *args, **kwargs):
        super().__init__(*args)

        self.requester = kwargs.get('requester')
        self.requested_at = kwargs.get('requested_at', datetime.utcnow())

    @property
    def thumbnail_url(self):
        """Return the thumbnail URL."""
        return self.thumb

    @property
    def youtube_id(self):
        """Return the track's YouTube id."""
        return self.ytid
