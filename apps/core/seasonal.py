import math
from datetime import date, timedelta
from functools import lru_cache

from django.utils import timezone
from django.db import ProgrammingError

from .models import SiteAppearance

THEME_CHOICES = [('auto', 'Tự động theo ngày lễ'), ('off', 'Không trang trí'),
                 ('christmas', 'Noel'), ('teachers-day', 'Ngày Nhà giáo Việt Nam'),
                 ('halloween', 'Halloween'), ('tet', 'Tết'), ('mid-autumn', 'Trung thu')]
THEMES = {key for key, _ in THEME_CHOICES} - {'auto', 'off'}


def _new_moon(k):
    t = k / 1236.85
    t2, t3 = t*t, t*t*t
    rad = math.pi / 180
    jd = 2415020.75933 + 29.53058868*k + .0001178*t2 - .000000155*t3
    jd += .00033 * math.sin((166.56 + 132.87*t - .009173*t2)*rad)
    m = 359.2242 + 29.10535608*k - .0000333*t2 - .00000347*t3
    mp = 306.0253 + 385.81691806*k + .0107306*t2 + .00001236*t3
    f = 21.2964 + 390.67050646*k - .0016528*t2 - .00000239*t3
    c = (.1734 - .000393*t)*math.sin(m*rad) + .0021*math.sin(2*m*rad)
    c -= .4068*math.sin(mp*rad) + .0161*math.sin(2*mp*rad)
    c -= .0004*math.sin(3*mp*rad) + .0104*math.sin(2*f*rad)
    c += .0004*math.sin((m+2*mp)*rad) - .0004*math.sin((m-2*mp)*rad)
    c -= .0006*math.sin((m+2*f)*rad)
    c += .0010*math.sin((m-2*f)*rad) + .0005*math.sin((2*mp+f)*rad)
    dt = .001 + .000839*t + .0002261*t2 - .00000845*t3 - .000000081*t*t3 if t < -11 else -.000278 + .000265*t + .000262*t2
    return math.floor(jd + c - dt + .5 + 7/24)


def _sun_sector(day):
    t = (day - .5 - 7/24 - 2451545.0) / 36525
    rad = math.pi / 180
    m = (357.52910 + 35999.05030*t - .0001559*t*t - .00000048*t*t*t)*rad
    longitude = (280.46645 + 36000.76983*t + .0003032*t*t + (1.914600 - .004817*t - .000014*t*t)*math.sin(m) + (.019993 - .000101*t)*math.sin(2*m) + .000290*math.sin(3*m))*rad
    return math.floor((longitude % (2*math.pi)) / math.pi * 6)


def _month_eleven(year):
    day = date(year, 12, 31).toordinal() + 1721425
    k = math.floor((day - 2415021.076998695) / 29.530588853)
    moon = _new_moon(k)
    return _new_moon(k-1) if _sun_sector(moon) >= 9 else moon


def _leap_offset(month11):
    k = math.floor((month11 - 2415021.076998695) / 29.530588853 + .5)
    previous = _sun_sector(_new_moon(k+1))
    for i in range(2, 15):
        current = _sun_sector(_new_moon(k+i))
        if current == previous:
            return i-1
        previous = current
    return 14


def lunar_date(day):
    jd = day.toordinal() + 1721425
    k = math.floor((jd - 2415021.076998695) / 29.530588853)
    start = _new_moon(k+1)
    if start > jd:
        start = _new_moon(k)
    a = _month_eleven(day.year)
    if a >= start:
        a = _month_eleven(day.year-1)
        b = _month_eleven(day.year)
    else:
        b = _month_eleven(day.year+1)
    diff = math.floor((start-a)/29)
    month = diff+11
    leap = False
    if b-a > 365:
        offset = _leap_offset(a)
        if diff >= offset:
            month = diff+10
            leap = diff == offset
    if month > 12:
        month -= 12
    return jd-start+1, month, leap


@lru_cache(maxsize=16)
def holidays(year):
    result = [(date(year, 10, 31), 'halloween'), (date(year, 11, 20), 'teachers-day'), (date(year, 12, 25), 'christmas')]
    day = date(year, 1, 1)
    while day.year == year:
        lunar_day, lunar_month, leap = lunar_date(day)
        if not leap and (lunar_day, lunar_month) in ((1, 1), (15, 8)):
            result.append((day, 'tet' if lunar_month == 1 else 'mid-autumn'))
        day += timedelta(days=1)
    return tuple(result)


def active_theme(selection, today=None):
    if selection != 'auto':
        return selection if selection in THEMES else ''
    today = today or timezone.localdate()
    upcoming = [(day, theme) for year in (today.year, today.year+1) for day, theme in holidays(year) if 0 <= (day-today).days <= 7]
    return min(upcoming)[1] if upcoming else ''


def context(request):
    try:
        selection = SiteAppearance.objects.filter(pk=1).values_list('theme', flat=True).first() or 'auto'
    except ProgrammingError as exc:
        # Keep public pages available until the new settings table is migrated.
        if getattr(exc.__cause__, 'sqlstate', None) != '42P01':
            raise
        selection = 'auto'
    return {'seasonal_theme': active_theme(selection)}
