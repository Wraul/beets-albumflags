from beets.plugins import BeetsPlugin
from beets import ui
from beets.ui.commands import _do_query
from beets.importer import action

from functools import reduce
import re


class Flag:
    """An abstract object representing a flag that can be present on an ablum.
    A flag should know how to remove itself from an album string and how to
    analyze an item to detect if the flag should be active.
    """

    _patterns = []

    def remove(self, album):
        return re.sub("|".join(self._patterns), "", album)

    def generate(self, item):
        return ""


class FieldMappingFlag(Flag):
    _field = ""
    _mapping = {}

    def __init__(self):
        super(FieldMappingFlag, self).__init__()
        self._patterns = map(lambda m: r" \(%s\)" % m, self._mapping.values())

    def generate(self, item):
        if self._field in item and item[self._field] in self._mapping:
            return " (%s)" % self._mapping[item[self._field]]
        else:
            return ""


class BitdepthFlag(Flag):
    _patterns = [
        r" \(\d+bit\)",
    ]

    def generate(self, item):
        if item.bitdepth >= 24:
            return " (%ibit)" % (item.bitdepth)
        else:
            return ""


class SamplerateFlag(Flag):
    _patterns = [
        r" \(\d+kHz\)",
    ]

    def generate(self, item):
        if item.samplerate > 44100:
            return " (%gkHz)" % (item.samplerate / 1000)
        else:
            return ""


class ChannelsFlag(Flag):
    _patterns = [
        r" \(5.1\)",
    ]

    def generate(self, item):
        if item.channels == 6:
            return " (5.1)"
        else:
            return ""


class MediaFlag(FieldMappingFlag):
    _field = "media"
    _mapping = {
        "Download": "Download",
        "Vinyl": "Vinyl",
        "BluRay": "BluRay",
        "CD-R": "CD-R",
    }


class StatusFlag(FieldMappingFlag):
    _field = "albumstatus"
    _mapping = {
        "Bootleg": "Bootleg",
        "Promotion": "Promo",
    }


class AlbumTypeFlag(FieldMappingFlag):
    _field = "albumtype"
    _mapping = {
        "demo": "Demo",
        "ep": "EP",
        "live": "Libe",
        "single": "Single",
        "soundtrack": "Soundtrack",
    }


CONFIG_FLAG_MAP = {
    "albumtype": AlbumTypeFlag,
    "status": StatusFlag,
    "media": MediaFlag,
    "channels": ChannelsFlag,
    "bitdepth": BitdepthFlag,
    "samplerate": SamplerateFlag,
}


class AlbumFlags(BeetsPlugin):
    def __init__(self):
        super(AlbumFlags, self).__init__()

        self._flags = []

        self.config.add({"auto": True} | {k: True for k in CONFIG_FLAG_MAP})

        for k, f in CONFIG_FLAG_MAP.items():
            if self.config[k].get():
                self._flags.append(f())

        if self.config["auto"]:
            self.register_listener("album_imported", self._import_album)
            self.register_listener("item_imported", self._import_item)

    def _remove_flags(self, album):
        """Remove all known flags from the provided album string"""
        return reduce(
            lambda new_album, flag: flag.remove(new_album), self._flags, album
        )

    def _generate_flags(self, item):
        """Generate a string with flags based on the items properties"""
        return "".join(flag.generate(item) for flag in self._flags)

    def commands(self):
        update_flags_command = ui.Subcommand("updateflags", help="update album flags")
        update_flags_command.parser.add_album_option()
        update_flags_command.func = self._update_flags_command
        return [update_flags_command]

    def _update_flags(self, item):
        self._log.debug("Updating flags for item: {0.id}: {0.title}", item)

        album = self._remove_flags(item.album)
        flags = self._generate_flags(item)
        album_with_flags = album + flags

        self._log.debug("Generated the following flags: {0}", flags)

        if item.album != album_with_flags:
            self._log.debug(
                'Changing album from "{0}" to "{1}"', item.album, album_with_flags
            )
            item.album = album_with_flags
            item.try_sync(ui.should_write(), ui.should_move())

        # Also write the changes to the parent album
        current_album = item.get_album()
        if current_album and current_album.album != album_with_flags:
            current_album.album = album_with_flags
            current_album.try_sync(ui.should_write(), ui.should_move())

    def _update_flags_command(self, lib, opts, args):
        query = ui.decargs(args)
        items, albums = _do_query(lib, query, opts.album, False)

        for item in items:
            # Reload the item as it could have changed due to us making changes to the parent album
            item.load()

            self._update_flags(item)

    def _import_album(self, lib, album):
        # Use the first item to determine a albums flags
        item, *tail = album.items()
        self._update_flags(item)

    def _import_item(self, lib, item):
        self._update_flags(item)

    def _update_flags_task(self, session, task):
        for item in task.items:
            self._update_flags(item)
        return action.RETAG
