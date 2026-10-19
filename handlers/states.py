from aiogram.fsm.state import State, StatesGroup


class MovieAdd(StatesGroup):
    code = State()
    title = State()
    description = State()
    media = State()
    extra_text = State()
    confirm = State()


class MovieEdit(StatesGroup):
    code = State()
    value = State()


class SeriesAdd(StatesGroup):
    code = State()
    title = State()
    description = State()
    episodes = State()


class SeriesEpisodeAdd(StatesGroup):
    code = State()
    episodes = State()


class SeriesEpisodeDelete(StatesGroup):
    code = State()


class AdminManage(StatesGroup):
    add_id = State()
    add_confirm = State()
    remove_id = State()
    remove_confirm = State()


class ChannelManage(StatesGroup):
    add = State()


class UserManage(StatesGroup):
    lookup = State()
    block_id = State()
    block_confirm = State()
    unblock_id = State()


class Broadcast(StatesGroup):
    message = State()
    confirm = State()


class SettingEdit(StatesGroup):
    value = State()


class PaymentSetup(StatesGroup):
    amount = State()
    instructions = State()


class PaymentProof(StatesGroup):
    proof = State()