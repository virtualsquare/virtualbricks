from virtualbricks import brickfactory, bricks


class BrickStub(bricks.Brick):

    def get_type(self):
        return "Stub"


class ConfigFileStub:

    def __init__(self, save=None, restore=None):
        self._save = save
        self._restore = restore

    def get_type(self):
        return "Stub"

    def restore(self, arg):
        if self._restore:
            self._restore(arg)

    def save(self, arg):
        if self._save:
            self._save(arg)


class FactoryStub(brickfactory.BrickFactory):

    restore_configfile_real = False

    def __init__(self):
        brickfactory.BrickFactory.__init__(self)
        self.BRICKTYPES["stub"] = BrickStub

    def restore_configfile(self):
        if self.restore_configfile_real:
            brickfactory.BrickFactory.restore_configfile(self)
