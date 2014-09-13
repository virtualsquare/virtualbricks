import gtk


class AbstractList:

    def __init__(self, view, value_member=""):
        self._view = view
        self._value_member = value_member

    def set_data_source(self, lst):
        model = self._view.get_model()
        model.clear()
        for row in lst:
            model.append((row, ))

    def add(self, value):
        model = self._view.get_model()
        model.append((value, ))

    def remove(self, value):
        model = self._view.get_model()
        mbr = self._value_member
        itr = model.get_iter_first()
        while itr:
            obj = model[itr][0]
            if (mbr and getattr(obj, mbr) == value) or obj == value:
                model.remove(itr)
                return
            itr = model.iter_next(itr)

    def on_changed(self, value):
        model = self._view.get_model()
        mbr = self._value_member
        itr = model.get_iter_first()
        while itr:
            obj = model[itr][0]
            if (mbr and getattr(obj, mbr) == value) or obj == value:
                model.row_changed(model.get_path(itr), itr)
                return
            itr = model.iter_next(itr)


class ListEntry:

    def __init__(self, value, label):
        self.value = value
        self.label = label

    @classmethod
    def from_tpl(cls, pair):
        return cls(*pair)

    def __format__(self, format_string):
        if format_string == "l":
            return str(self.label)
        elif format_string == "v":
            return str(self.value)
        raise ValueError("Invalid format string " + repr(format_string))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.value == other.value and self.label == other.label

    def __ne__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return not self.__eq__(other)


class ListControl(AbstractList):

    def __init__(self, view, formatting_enabled=False, format_string="",
                 formatter=None, display_member="", value_member=""):
        AbstractList.__init__(self, view, value_member)
        self._formatting_enabled = formatting_enabled
        self._format_string = format_string
        self._formatter = formatter
        self._display_member = display_member

    @classmethod
    def for_entry(cls, view):
        return cls(view, display_member="label", value_member="value")

    @classmethod
    def with_fmt(cls, view, format_string, formatter=None):
        return cls(view, formatting_enabled=True, format_string=format_string,
                   formatter=formatter)

    def get_formatting_enabled(self):
        return self._formatting_enabled

    def set_formatting_enabled(self, value):
        self.format._formatting_enabled = bool(value)

    def get_format_string(self):
        return self._format_string

    def set_format_string(self, value):
        self._format_string = str(value)

    def get_formatter(self):
        return self._formatter

    def set_formatter(self, value):
        self._formatter = value

    def _set_cell_data(self, celllayout, cell, model, itr, data=None):
        obj = model[itr][0]
        if self._formatting_enabled:
            if self._formatter is not None:
                text = self._formatter.format(self._format_string, obj)
            else:
                text = format(obj, self._format_string)
        elif self._display_member and obj is not None:
            text = str(getattr(obj, self._display_member))
        else:
            text = str(obj)
        cell.set_property("text", text)


class ComboBox(ListControl):

    def __init__(self, view, *args, **kwds):
        ListControl.__init__(self, view, *args, **kwds)
        view.set_cell_data_func(view.get_cells()[0], self._set_cell_data)

    def _changed(self):
        itr = self._view.get_active_iter()
        if itr:
            model = self._view.get_model()
            model.row_changed(model.get_path(itr), itr)

    def get_selected_index(self):
        return self._view.get_model().get_index()

    def set_selected_index(self, idx):
        return self._view.get_model().set_index(idx)

    def get_selected_value(self):
        model = self._view.get_model()
        itr = self._view.get_active_iter()
        if itr:
            obj = model[itr][0]
            if self._value_member:
                return getattr(obj, self._value_member)
            else:
                return obj

    def set_selected_value(self, value):
        model = self._view.get_model()
        itr = model.get_iter_first()
        while itr:
            obj = model[itr][0]
            mbr = self._value_member
            if (mbr and getattr(obj, mbr) == value) or obj == value:
                self._view.set_active_iter(itr)
                break
            itr = model.iter_next(itr)


SELECT_ALL = object()
SELECT_NONE = object()


class ListStore(ListControl):

    def __init__(self, view, *args, **kwds):
        ListControl.__init__(self, view, *args, **kwds)
        col = view.get_column(0)
        cell = col.get_cell_renderers()[0]
        col.set_cell_data_func(cell, self._set_cell_data)

    def get_selected_values(self):
        selection = self._view.get_selection()
        mode = selection.get_mode()
        if mode == gtk.SELECTION_NONE:
            return ()
        elif mode in (gtk.SELECTION_SINGLE, gtk.SELECTION_BROWSE):
            model, itr = selection.get_selected()
            if itr is None:
                return ()
            if self._value_member:
                return getattr(model[itr][0], self._value_member)
            else:
                return model[itr][0]
        else:
            model, paths = selection.get_selected_rows()
            mbr = self._value_member
            if mbr:
                return tuple(getattr(model[path][0], mbr) for path in paths)
            else:
                return tuple(model[path][0] for path in paths)

    def set_selected_values(self, iterable):
        selection = self._view.get_selection()
        mode = selection.get_mode()
        if iterable is SELECT_ALL:
            if mode != gtk.SELECTION_MULTIPLE:
                raise ValueError("Cannot select all the nodes")
            selection.select_all()
        elif iterable is SELECT_NONE:
            selection.unselect_all()
        elif mode == gtk.SELECTION_NONE:
            raise ValueError("Cannot select any node")
        else:
            model = self._view.get_model()
            mbr = self._value_member
            selection.unselect_all()
            for value in iter(iterable):
                itr = model.get_iter_first()
                while itr:
                    obj = model[itr][0]
                    if (mbr and getattr(obj, mbr) == value) or obj == value:
                        selection.select_iter(itr)
                    itr = model.iter_next(itr)


class MulticolListStore(AbstractList):
    pass
