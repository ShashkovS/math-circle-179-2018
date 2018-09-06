import subprocess
import xlrd
import pickle
from collections import defaultdict
from functools import lru_cache
from pdf417gen import encode, render_image
from CONSTS import *
from BIN_PATH import *
import logging
import re
import sys
import zlib
logging.basicConfig(level=logging.INFO)
lg = logging.getLogger('ВМШ')

try:
    START_PATH = os.path.realpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '..'))
except NameError:
    pass
os.chdir(START_PATH)


@lru_cache()
def def_real_level(xls_level):
    level_search = [wrk['excel_level_const'] for wrk in work if xls_level in wrk['other_excel_level_const']]
    if len(level_search) != 1:
        lg.fatal('Что-то совсем не так с настройками уровня в CONST и xls: ' + xls_level)
        return None
    return level_search[0]


def compile_tex(filename, add_path=''):
    texify_path = TEXIFY_PATH
    texify_path = '"' + texify_path + '"'
    tex_file_path = os.path.join(START_PATH, add_path, filename)
    tex_file_path = '"' + tex_file_path + '"'
    swithches = ('--pdf', '--src-specials',
                 '--tex-option="--tcx=CP1251 --enable-write18 --shell-escape  --interaction=nonstopmode"')  ###
    lg.info('Компилим ' + tex_file_path)
    p = subprocess.Popen(' '.join([texify_path, *swithches, tex_file_path]),
                         cwd=os.path.join(START_PATH, add_path),
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE)
    output, err = p.communicate(timeout=100)

    if b'failed' in err:
        lg.error('Не удалось скомпилировать ' + filename)
        log = open(os.path.join(START_PATH, add_path, filename).replace('.tex', '.log'), 'r', encoding='utf-8',
                   errors='ignore')
        for row in log:
            if row.startswith('! ') or row.startswith('l.'):
                lg.error(row.strip())
        lg.fatal(err.decode('utf-8', errors='ignore').strip())

        return None

    for row in output.splitlines():
        if b'Output written' in row:
            lg.info(row.decode('utf-8'))
            return row.decode('utf-8')


def pdf2png(filename, add_path='', dest=None):
    gs_path = GS_PATH
    gs_path = '"' + gs_path + '"'
    pdf_file_path = os.path.join(START_PATH, add_path, filename)
    pdf_file_path = '"' + pdf_file_path + '"'
    if dest is None:
        dest = filename + '.png'
    swithches = ('-sDEVICE=png16m', '-dTextAlphaBits=4', '-r300', '-o', dest)
    print('Конвертим', filename)
    p = subprocess.Popen(' '.join([gs_path, *swithches, pdf_file_path]),
                         cwd=os.path.join(START_PATH, add_path),
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE
                         )
    output, err = p.communicate()
    for row in output.splitlines():
        if b'Page' in row:
            print(row.decode('utf-8'))
    print(err.decode('utf-8'))


def cond_color(val):
    if 0 <= val <= 0.5:
        val *= 2
        return (round((1 - val) * 248 + val * 255),
                round((1 - val) * 105 + val * 235),
                round((1 - val) * 107 + val * 132))
    elif 0.5 <= val <= 1:
        val = 2 * val - 1
        return (round((1 - val) * 255 + val * 99),
                round((1 - val) * 235 + val * 190),
                round((1 - val) * 132 + val * 123))
    else:
        print('АААА! Число больше 1')


def check_ids_unique(res):
    lg.info('Проверяем уникальность ID')
    print(res)
    ids = {}
    for i, row in enumerate(res):
        orig_id = str(row['ID'])
        dig_id = re.sub(r'[^0-9]', '', orig_id)[-4:].lstrip('0')
        if not dig_id:
            lg.error('В строке {} находится ID школьника {}, в котором нет ненулевых цифр. Они нужны!'.format(i + FIRST_ROW, orig_id))
            sys.exit()
        if dig_id in ids:
            lg.error('В строках {} и {} находятся «одинаковые» ID {} и {}. Правые 4 цифры должны быть уникальны'.format(
                ids[dig_id] + FIRST_ROW, i + FIRST_ROW, res[ids[dig_id]]['ID'], orig_id))
            sys.exit()
        ids[dig_id] = i
        res[i]['IDd'] = dig_id.zfill(4)


def parse_xls_conduit(fn):
    """Вычитывает данные из кондуита. Возвращает список постолцовых словарей"""
    lg.info('Открываем файл (займёт время) ' + fn)
    rb = xlrd.open_workbook(fn)
    sheet = rb.sheet_by_index(0)
    res = []
    lg.info('Вычитываем файл ' + fn)
    for rown in range(FIRST_ROW - 1, sheet.nrows):
        d_row = {key: str(sheet.cell(rown, coln).value).strip().replace('.0', '') for key, coln in COLUMNS.items()}
        lg.debug(d_row)
        #  lg.info(d_row)
        if type(d_row['Фамилия']) == str and d_row['Фамилия'].upper() != d_row['Фамилия']:
            d_row['ФИО'] = d_row['Фамилия'].title() + ' ' + d_row['Имя'].title()
            d_row['ФИ.'] = d_row['Фамилия'].title() + ' ' + d_row['Имя'].title()[0] + '.'
            d_row['Строчка'] = rown
            #    d_row['Класс'] =
            res.append(d_row)
    lg.info('Файл вычитан ' + fn)
    check_ids_unique(res)
    return res


def tree():
    return defaultdict(tree)


def read_stats() -> object:
    pickle_dump_path = os.path.join(DUMMY_FOLDER_PATH, 'zstats.pickle')
    try:
        with open(pickle_dump_path, 'rb') as f:
            stats = pickle.load(file=f)
    except FileNotFoundError:
        dd = tree()
        with open(pickle_dump_path, 'wb') as f:
            pickle.dump(dd, file=f)
        stats = dd
    return stats


def update_stats(stats):
    pickle_dump_path = os.path.join(DUMMY_FOLDER_PATH, 'zstats.pickle')
    with open(pickle_dump_path, 'wb') as f:
        pickle.dump(stats, file=f)


def crt_aud_barcode(aud, ids):
    ELEM_LEN = 4
    data_d = [id.zfill(ELEM_LEN)[-ELEM_LEN:] for id in ids]
    to_save_s = str(aud).zfill(ELEM_LEN) + ''.join(data_d)
    to_save_b = to_save_s.encode()
    to_save_z = zlib.compress(to_save_b)
    codes = encode(to_save_z, columns=28, security_level=5)
    image = render_image(codes, scale=1, padding=0)
    image.save(os.path.join(DUMMY_FOLDER_PATH, BARCODES, 'barcode_{}.png'.format(aud)))