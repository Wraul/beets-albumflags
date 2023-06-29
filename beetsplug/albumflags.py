from beets.plugins import BeetsPlugin
from beets import ui
from beets.ui.commands import _do_query

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
    def __init__(self, field, mapping):
        self._field = field
        self._mapping = mapping

    def remove(self, album):
        patterns = map(lambda m: r" \(%s\)" % m, self._mapping.values())
        return re.sub("|".join(patterns), "", album)

    def generate(self, item):
        if self._field in item and item[self._field] in self._mapping:
            return " (%s)" % self._mapping[item[self._field]]
        else:
            return ""


class BitdepthFlag(Flag):
    _patterns = [
        r" \(\d+bit\)",
    ]

    def __init__(self, min_bitdepth):
        self._min_bitdepth = min_bitdepth

    def generate(self, item):
        if item.bitdepth >= self._min_bitdepth:
            return " (%ibit)" % (item.bitdepth)
        else:
            return ""


class SamplerateFlag(Flag):
    _patterns = [
        r" \(\d+kHz\)",
    ]

    def __init__(self, min_samplerate):
        self._min_samplerate = min_samplerate

    def generate(self, item):
        if item.samplerate >= self._min_samplerate:
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





class AlbumFlags(BeetsPlugin):
    def __init__(self):
        super(AlbumFlags, self).__init__()

        self._flags = []

        self.config.add(
            {
                "auto": True,
                "flags": [],
                "field_flags": {},
                "bitdepth_flag": {"min_bitdepth": 24},
                "samplerate_flag": {"min_samplerate": 96000},
            }
        )

        field_flags = self.config["field_flags"].get()

        for f in self.config["flags"].get():
            category, field = f.split(":") if ":" in f else [f, None]

            if category == "field" and field in field_flags:
                self._flags.append(FieldMappingFlag(field, field_flags[field]))
            elif category == "bitdepth":
                self._flags.append(
                    BitdepthFlag(self.config["bitdepth_flag"]["min_bitdepth"].get())
                )
            elif category == "samplerate":
                self._flags.append(
                    SamplerateFlag(
                        self.config["samplerate_flag"]["min_samplerate"].get()
                    )
                )
            elif category == "channels":
                self._flags.append(ChannelsFlag())

        if self.config["auto"].get():
            self.register_listener("album_imported", self._import_album)
            self.register_listener("item_imported", self._import_item)

    def _remove_flag_string(self, album):
        """Remove all known flags from the provided album string"""
        return reduce(
            lambda new_album, flag: flag.remove(new_album), self._flags, album
        )

    def _generate_flag_string(self, item):
        """Generate a string with flags based on the items properties"""
        return "".join(flag.generate(item) for flag in self._flags)

    def commands(self):
        update_flags_command = ui.Subcommand("updateflags", help="update album flags")
        update_flags_command.parser.add_album_option()
        update_flags_command.func = self._update_flags_command

        remove_flags_command = ui.Subcommand("removeflags", help="remove album flags")
        remove_flags_command.parser.add_album_option()
        remove_flags_command.func = self._remove_flags_command

        return [update_flags_command, remove_flags_command]

    def _update_flags(self, item):
        self._log.debug("Updating flags for item: {0.id}: {0.title}", item)

        album = self._remove_flag_string(item.album)
        flags = self._generate_flag_string(item)
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

    def _remove_flags(self, item):
        self._log.debug("Removing flags for item: {0.id}: {0.title}", item)

        album_without_flags = self._remove_flag_string(item.album)

        if item.album != album_without_flags:
            self._log.debug(
                'Changing album from "{0}" to "{1}"', item.album, album_without_flags
            )
            item.album = album_without_flags
            item.try_sync(ui.should_write(), ui.should_move())

        # Also write the changes to the parent album
        current_album = item.get_album()
        if current_album and current_album.album != album_without_flags:
            current_album.album = album_without_flags
            current_album.try_sync(ui.should_write(), ui.should_move())

    def _update_flags_command(self, lib, opts, args):
        query = ui.decargs(args)
        items, albums = _do_query(lib, query, opts.album, False)

        for item in items:
            # Reload the item as it could have changed due to us making changes to the parent album
            item.load()

            self._update_flags(item)

    def _remove_flags_command(self, lib, opts, args):
        query = ui.decargs(args)
        items, albums = _do_query(lib, query, opts.album, False)

        for item in items:
            # Reload the item as it could have changed due to us making changes to the parent album
            item.load()

            self._remove_flags(item)

    def _import_album(self, lib, album):
        # Use the first item to determine a albums flags
        item, *tail = album.items()
        self._update_flags(item)

    def _import_item(self, lib, item):
        self._update_flags(item)
