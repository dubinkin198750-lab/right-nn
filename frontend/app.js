// Три этапа процесса (претензия / первое обращение / повторное обращение)
// используют один и тот же набор решений — см. backend/storage.py
// APPEAL_DECISIONS (держать в одном порядке с бэкендом). Общего единого
// «Статуса» дела больше нет.
const APPEAL_DECISIONS = ["", "заблокировано", "отклонено", "нет реакции"];

// Справочник известных ответчиков (хостинг/CDN-провайдеров и площадок) —
// название на языке оригинала с транслитерацией в скобках + адрес
// регистрации билингвально (как уже принято в поле «Адрес ответчика» в
// этом приложении). Используется для автоподсказки в поле «Ответчик» в
// разделе «Блокировка»: строка вводится/выбирается один раз, и вместе с
// ней сразу заполняется соответствующий адрес — не нужно искать и
// перепечатывать вручную каждый раз одну и ту же организацию.
// Собрано из реально поданных заявлений в Мосгорсуд (справочник
// ответчиков, который прикладывался к каждому заявлению) — объединены и
// очищены от дублей/опечаток по всем присланным примерам (Андрианов,
// Белоусова, Гордынец, Гофман, Журнал «Думай», Федяев). 85 организаций.
const KNOWN_DEFENDANTS = [
  { name: '3Nt Solutions Llp (ООО Решения 3Nt)', address: 'Ketelskamp 10, Meppel, NL. Кателскамп, 10, Меппель, Северная Каролина.' },
  { name: 'Ab Stract (Аб Стрэкт)', address: 'Urho Kekkosen Katu 4-6E, 00100, Helsinki, Finland. Урхо Кеккосен Кату 4-6E, 00100, Хельсинки, Финляндия.' },
  { name: 'Aberystwyth University (Аберистуитский университет)', address: 'Old College, King Street, Aberystwyth, Ceredigion, Sy23 2Ax. Старый колледж, Кинг-стрит, Аберистуит, Кередигион, Sy23 2Ax.' },
  { name: 'Aeza International Ltd (Компания Aeza International Ltd)', address: '311 Shoreham Street, Sheffield, S2 4Fa, United Kingdom. 311 Шорхэм Стрит Шеффилд, S2 4Fa, Соединенное Королевство.' },
  { name: 'Alexhost Srl (АлексХост)', address: 'Str. C. Brancusi Nr. 3, Chisinau, Moldova. Стр. C. Brancusi Нет. 3, Кишинев, Молдова.' },
  { name: 'Amarutu Technology Ltd. Network (Сеть компании Амаруту Технологии)', address: 'Level 23, One Island East, 18 Westlands Road, N/A, Hong Kong, Hong Kong. Уровень 23, Восточный остров, Уэстлендс-роуд, 18, N/A, Hong Kong, Hong Kong.' },
  { name: 'Amsterdam, Netherlands (Амстердам, Нидерланды)', address: 'United Arab Emirates, Dubai, 336469, Ifza Business Park Ddp, Building 1, Office Number 36298-001. Объединённые Арабские Эмираты, Дубай, 336469, бизнес-парк Ifza Ddp, здание 1, офис № 36298-001.' },
  { name: 'Beget Ltd (Бегет ЛТД)', address: '199034, Россия, Санкт-Петербург, 2-я линия Васильевского острова, строение 5, литера А, оф. 11н' },
  { name: 'Bel Ombre Rd. P.5057 (Бель Омбр Роуд, стр. 5057)', address: 'Bel Ombre Rd. P.5057, NA, Beau Vallon, Seychelles. Бель Омбре Роуд. P.5057, NA, Бо Валлон, Сейшельские острова.' },
  { name: 'Bluehost Inc (Блюхост Инк)', address: '1958 South 950 East, Provo, UT, 84606, US. 1958 Юг 950 Восток, Прово, Юта, 84606, США.' },
  { name: 'Buyvm (Байвм)', address: '1621 Central Ave, 3, Op Der Poukewiss, Roost, WY, 7795, LU. Центральный проспект 1621, 3, Оп-дер-Поукевисс, Руст, WY, 7795, ЛУ' },
  { name: 'Bytefilter Llc (ООО Байтфильтр)', address: '500 Westover Dr #32833, 530-B Harkle Road, Suite 100, Santa Fe, NM, 87505, US. 500 Вестовер Драйв, 530-B Харкл Роуд, Люкс 100, Санта-Фе, Нью-Йорк, 87505, Соединенные Штаты Америки.' },
  { name: 'Celeritas International Llc (ООО "Селеритас Интернэшнл")', address: 'Str. Bistntei Nr. 3, Cluj-Napoca, 400430, Romania. Ул. Биштней, 3, Клуж-Напока, 400430, Румыния.' },
  { name: 'CloudFlare Inc. (КлаудФлэр Инк.)', address: '101 Townsend St, San Francisco, CA 94107, USA (101 Тоунсенд стрит, Сан Франциско, СА 94107, США)' },
  { name: 'Compubyte Limited (Компубайт Лимитед)', address: 'Барклая, Дом 6, Строен.5, Оф. 408, 121087, Москва, Российская Федерация' },
  { name: 'Connexly Llc (ООО "Коннексли")', address: 'Gncs - Whq, 864 Spring Street, Po Box 1520, Zephyr Cove, NV, 89448, US. Gncs - штаб-квартира, Спринг-стрит, 864, почтовый ящик 1520, Зефир-Коув, Невада, 89448, США.' },
  { name: 'Contabo Gmbh (Контабо гмбх)', address: 'Aschauer Str. 32A, 81549 Muenchen, Germany. Ул. Ашауэр 32А, 81549, Мюнхен, Германия.' },
  { name: 'Cyber Folks S.a (Кибер фолкс С.а.)', address: 'Ul. Wierzbi?Cice 1B, 61-569, Poznan, Poland. Ул. Вержби?Цице, 1Б, 61-569, Познань, Польша.' },
  { name: 'Datahouse.ru Network (Датахаус.ру Сеть)', address: '105120 Россия, Москва, Электролитный переулок, 3/47.' },
  { name: 'DDOS-GUARD LTD (ООО «ДДОС-ГВАРД»)', address: 'Ул. Максима Горького 279, Этаж 5, Оф. 11, 344019, Ростов-На-Дону, Российская Федерация.' },
  { name: 'Dedicated.com (Посвященный.ком)', address: '910 W Van Buren Suite 610, 4400 Ne 77Th Ave Ste 275, Vancouver, WA, 98662, US. 910 Вт Ван Бюрен Люкс 610, 4400 Ne 77-я авеню, Ste 275, Ванкувер, Вашингтон, 98662, США.' },
  { name: 'Elserver.com (Элсервер.ком)', address: 'La Rioja, 301, C1214Adb - Capital Federal - Ba, AR. Ла-Риоха, 301, C1214Adb --- Федеральная столица --- Ба, Аргентина.' },
  { name: 'Enayati, Sean (Энаяти, Шон)', address: '201 East 16Th Ave, 201 E. 16Th St, North Kansas City, MO, 64116, US. 201 Ист-16-я авеню, 201 Ист-16-я улица, Северный Канзас-Сити, Миссури, 64116, США.' },
  { name: 'EuroHoster Ltd. (ЕвроХостер Лтд.)', address: '48, Angel Dimitrov str., apt. 2, Burgas, 8016, Bulgaria. Ул. Святых Кирилла и Мефодия, 5 1 этаж, офис 3, 8000, Бургас, Болгария.' },
  { name: 'Fornex Hosting S.l (Форнекс Хостинг)', address: 'Cabo Bermejo 1721, 29680 Estepona, Spain. Кабо-Бермехо 1721, 29680 Эстепона, Испания.' },
  { name: 'Free Sas (Бесплатный Sas)', address: '8 Rue De La Ville L\\\'Eveque, 75008 Paris, France. Улица Виль-Л\\\'Эвек, 8, 75008 Париж, Франция.' },
  { name: 'Friendhosting LTD (ООО Френдхостинг)', address: 'sv. Cyril And Methodius Block 5, Floor 1, Ap. Left, 8000, Burgas, BulgariaSv.sv. Cyril And Methodius Block 5, Floor 1, Ap. Left, 8000, Burgas, Bulgaria. Кирилло-МефодиевскийБлок 5, Этаж 1, Ап. Левый, 8000, Бургас, Болгария' },
  { name: 'Ginernet (Джинернет)', address: 'Albasanz 65, 28037, Madrid, Spain. Альбасанц 65, 28037, Мадрид, Испания.' },
  { name: 'GoDaddy.com, LLC (ООО «Го Дедди»)', address: '14455 N. HaydenRd., Ste. 226 Scottsdale, AZ 85260 USA (США).' },
  { name: 'Green Floid LLC (ООО "Грин Флойд")', address: '2707 East Jefferson St, Orlando, Florida, 32803, USA (2707 Ист Джефферсон стрит, Орландо, Флорида, 32803, США)' },
  { name: 'Home.pl Sp. z o.o.', address: 'Zbozowa 4, 70-653 Szczecin, Poland. Жбожова 4, 70-653 Щецин, Польша.' },
  { name: 'Hooray Solutions Corp (Хюрей Солюшин корп)', address: 'New Horizon Building, первый этаж, 3 1/2 мили Philip S. w. GoldsonHighway, Белиз-Сити, Белиз.' },
  { name: 'Host Spa (Хостинг Спа)', address: 'Corso Svizzera 185, 10149, Torino, Italy. Корсо Свитцера, 185, 10149, Турин, Италия.' },
  { name: 'Hostiman.ru (Хостиман.ру)', address: '241050, Брянская обл., Брянск, 132' },
  { name: 'Hosting Provider Eurohoster Ltd (Хостинг-провайдер Eurohoster Ltd)', address: '5 St. Cyril And Methodius Str. 1St Floor, Office 3, 8000, Burgas, Bulgaria. Ул. Св. Кирилла и Мефодия, 5, 1-й этаж, офис 3, 8000, Бургас, Болгария.' },
  { name: 'Hosting Technology Ltd (ООО «Хостинг-технологии»)', address: '109202, Россия, г.Москва, 1-ая Фрезерная улица, дом 2/1 корпус 2.' },
  { name: 'Hostline (Хост-линия)', address: '105120 Россия Москва, Электролитный Пр., 3/47.' },
  { name: 'Infolink Technology (Технология Инфолинк)', address: '141170, г. Мытищи, ул. В. О. Ленина, д. 15, стр. 2.' },
  { name: 'Internet Archive (Интернет-архив)', address: '300 Funston Ave. San Francisco, CA, 94118, US. 300 Фанстон-авеню, Сан-Франциско, Калифорния, 94118, США' },
  { name: 'Internet Invest Ltd. (Интернет Инвест Лтд)', address: '01033, Украина, г. Киев, ул. Гайдара, д. 50' },
  { name: 'Ip Vendetta Inc (Ип вендетта инк)', address: '306 Victoria House, Victoria Mahe, Seychelles. 306 Виктория Хаус Виктория Маэ, Сейшельские острова.' },
  { name: 'Iqweb - Llc Net (Сеть Iqweb -- Ооо)', address: 'United Arab Emirates, Dubai, 00000, Dubai Internet City 3. Объединенные Арабские Эмираты, Дубай, 00000, Dubai Internet City 3.' },
  { name: 'Iroko Networks Corporation (Корпорация Iroko Networks)', address: '63/66 Hatton Garden, Suite 23, London, аEc1N 8Le, United Kingdom. 63/66 Хаттон-Гарден, Люкс 23, Лондон, Ес1в 8 Ли, Великобритания.' },
  { name: 'Jsc Datacenter (АО " Центр обработки данных ")', address: 'Нагорное шоссе, 2, 141400, Химки, Московская область, Российская Федерация.' },
  { name: 'Jsc North - West Telecom, Arkhangelsk Branch (АО «Северо-Западный Телеком», Архангельский филиал)', address: 'АО «Северо-Западный Телеком», Архангельский филиал, ул. Ломоносова, д. 142, офис 617, 163061, Архангельск, Россия.' },
  { name: 'JSC Rtcomm.ru (ОАО Rtcomm.ru)', address: 'Делегатская ул., д. 5, стр. 1, 127473 Москва, Российская Федерация.' },
  { name: 'Korea Telecom (Корейский телеком)', address: '206, Jungja-Dong, Bundang-Gu, Sungnam-Ci, 463-711. 206, Юнгджа-Дон, Бунданг-Гу, Суннам-Си, 463-711.' },
  { name: 'Laevastiku 1L (Флот 1L)', address: 'Laevastiku 1L, 10313, Tallinn, Estonia. Флот 1L 10313, Таллинн, Эстония.' },
  { name: 'Leaseweb Usa, Inc (Леасовеб США, Инк)', address: '9301 Innovation Drive / Suite 100 Manassas, VA 20110 (9301, США, штат Вирджиния, город Манассас, Innovation Dr, 20109,)' },
  { name: 'Limited Liability Company Vk (Общество с ограниченной ответственностью Вк)', address: '125167, Россия , Москва, Ленинградский проспект, 39/79.' },
  { name: 'NetAssist LLC (ООО "НетАссист")', address: '04213, Украина, Киев, бульвар Маршала Рокоссовского, д.3.' },
  { name: 'Nextgenwebs, S.L (Некстгенвебс, Южная Каролина)', address: 'Plaza Gerardo Salvador 1, 46988, Патерна, Испания. Площадь Херардо Сальвадора 1, 46988, Патерна, Испания.' },
  { name: 'Njalla (Ньялла)', address: 'Box 4111, 203 12 Malmo, Sweden. Box 4111, 203 12 Мальме, Швеция.' },
  { name: 'Novoserve B.v (Новосерв Б. в)', address: 'Gildenbroederslaan 1, 7005 Bm, Doetichem, Netherlands. Гильденбредерслаан 1, 7005 бм, Доэтичем, Нидерланды.' },
  { name: 'On-Line Data Ltd (Он - Лайн дата)', address: 'Suite 1, 8731069, Виктория, Сейшельские Острова' },
  { name: 'Ovh Sas (Овх сас)', address: '140 Quai Du Sartel, 59100 Roubaix, France. 140 Набережная Сартель, 59100 Рубе, Франция.' },
  { name: 'Podaon Sia (Подаон Сия)', address: 'Ernesta Birznieka-Upisa 18, Lv-1050, Riga, Latvia. Эрнеста. Бирзниека-Upisa 18, Lv-1050, Рига, Латвия.' },
  { name: 'Private Customer (Частный Клиент)', address: 'Частная Резиденция, США.' },
  { name: 'Private Layer Inc (Частный Слой Inc)', address: 'Edif. Ocean Business Plaza, 1404, Marbella, 00000 - Panama City -- Pa;Эдиф.Океанбизнесплощадь, 1404, Марбелья, 00000 - Панама-Сити--Пенсильвания.' },
  { name: 'Rambler Internet Holding OJSC (ОАО "Рамблер Интернет Холдинг")', address: 'Варшавское шоссе, 9, Строение 1, Москва, Россия' },
  { name: 'Rax.ru Internet Center (Rax.ru Интернет-центр)', address: 'Бутырский вал, 5-305, 127055, Москва, Российская Федерация.' },
  { name: 'Ru-Center Jsc (АО «Ру-Центр»)', address: 'Российская Федерация, 123308, Москва, ул. Хорошевская, д. 3, стр. 2-1' },
  { name: 'Safe Value Limited (Сейф Валью Лимитед)', address: 'Global Gateway 8, Rue De La Perle, Providence, Mahe, Seychelles. Глобалгетвэй 8, Ру Де Ла Перл, Провиденс, Махе, Сейшельские острова.' },
  { name: 'Sc Infotech - Grup Srl (Компания Sc Infotech - Grup Srl)', address: 'ул. Мунчешты 364, М. Кишинёв, Р. Молдова.' },
  { name: 'SELECTEL-NET (Сеть Селектель)', address: 'Россия, Санкт-Петербург, ул. Цветочная, 21' },
  { name: 'Servers Tech Fzco (Серверы Tech Fzco)', address: 'Ifza Business Park Ddp, Building 1, Office Number 36298-001, 336469, Dubai, United Arab Emirates. Бизнес-парк Ifza, здание 1, офис 36298-001, 336469, Дубай, Объединённые Арабские Эмираты.' },
  { name: 'Snowd Security Ou (Подразделение безопасности Snowd)', address: 'Punane Tn 56 Harju Maakond Lasnamäe Linnaosa, 13619, Tallinn, Estonia. Пунане, 56, Харьюский уезд, Ласнамяэ, 13619, Таллин, Эстония.' },
  { name: 'Spacecore Solution Ltd (Компания Spacecore Solution Ltd)', address: '71-75 Shelton Street, Covent Garden, London, United Kingdom, Wc2H 9Jq. Шелтон-стрит, 71--75, Ковент-Гарден, Лондон, Великобритания, Wc2H 9Jq.' },
  { name: 'Stark Industries Solutions Ltd', address: '71-75, Шелтон-стрит, Ковент-Гарден, Лондон, Wc2H 9Jq, Великобритания.' },
  { name: 'Sucuri (Сукури)', address: '30141 Antelope Road, Suite D, Menifee, California 92854, USA. 30141 Антилоп-роуд, Люкс D, Менифи, Калифорния 92854, США.' },
  { name: 'Telegram FZ-LLC (Телеграм Фз-Лк)', address: '501919 Business Central Towers, Tower A, Office 1003/1004, P. O. Box 501919, Dubai, UnitedArabEmirates (Башни Делового центра, Башня А, офис 1003/1004, Почтовый ящик 5019, Дубай, Объединенные Арабские Эмираты)' },
  { name: 'Telegram Messenger Network (Сеть Мессенджеров Telegram)', address: 'P.o. Box 146, Road Town, Tortola, British Virgin Islands (Почтовый ящик 146, Роуд-Таун, Тортола, Британские Виргинские острова).' },
  { name: 'TimeWeb Co. Ltd (ТаймВеб Лтд)', address: '196084, Россия, Санкт-Петербург, ул. Заставская, 22А.' },
  { name: 'Total Brands Limited (Всего брендов Ограничено)', address: 'Olaiji Shopping Center, 1St Floor, Victoria, Mahe, Seychelles. Торговый центр Олайджи, 1 этаж, Виктория, Маэ,Сейшельские острова.' },
  { name: 'Ufo Hosting Llc (ООО "Нло Хостинг")', address: 'Ул. Промышленная, д. 1, офис 113, 142305, деревня Сергеево, Российская Федерация.' },
  { name: 'Ultahost, Inc. (Ультахост Инк)', address: '308 Brollo Rd, Tunney, Germiston, 1614, South Africa. 308 Бролло-роуд, Танни, Джермистон, 1614, Южная Африка.' },
  { name: 'VDSINA VDS Hosting (ООО «Хостинг-технологии»)', address: '109202, Россия, г. Москва, 1-ая Фрезерная улица, дом 2/1 корпус 2' },
  { name: 'Vercel, Inc (Версель Инк)', address: '340 S Lemon Ave #4133, Walnut, CA, 91789, US. 340 S Лемон авеню #4133, Уолнат, Калифорния, 91789, США.' },
  { name: 'Webhost Llc (ООО "Вебхост")', address: 'Летниковская, д. 10, стр. 2, 115114, Москва, Российская Федерация' },
  { name: 'Worktitans Bv (Рабочие титаны Bv)', address: 'Hoge Bothofstraat 39, 7511 Za Enschede, Netherlands. Хоге Ботхофстраат 39, 7511 За-Энсхеде, Нидерланды.' },
  { name: 'Zomro B.V. (Зомро Б.В.)', address: 'Частная компания с ограниченной ответственностью Zomro B.V. (ЗомроБ.В.); Gildenbroederslaan 1, 7005 BM, Doetinchem, the Netherlands (Гилденброэдэрслан 1, 7005 BM, Дутинхем, Нидерланды)' },
  { name: 'ООО Reg.ru «Регистратор доменных имён РЕГ.РУ»', address: '125315, Моска, Ленинградский пр-кт, 72, 3.' },
  { name: 'ООО «Адман»', address: 'Ул. Митинская, д. 16, эт. 8, пом. 801Б, ком. 1-2, 125430, г. Москва, Российская Федерация.' },
  { name: 'ООО «Яндекс»', address: '119021, Российская Федерация, Г. Москва, Ул. Льва Толстого, Д. 16' },
  { name: 'Сервисы Вконтакте', address: 'Прем.1-Н, корп. 12-14, лит. А, Херсонская ул., 191024, Санкт-Петербург, Российская Федерация.' },
];


const state = {
  authors: [],
  worksByAuthor: {}, // author_id -> [work, ...]
  collapsed: {}, // author_id -> bool
  activeWorkId: null,
  activeAuthorId: null,
  polling: null,
  currentPipeline: null,
  currentJobId: null,
  currentScope: "filtered",
  savedResults: [],
  role: null,
  authEnabled: false,
  blockingSelection: new Set(),
};

const $ = (sel) => document.querySelector(sel);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Ошибка запроса: ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

function shortenUrl(url, maxLen = 58) {
  // Полный URL остаётся в href и в title (подсказка при наведении) —
  // здесь только то, что видно глазом в таблице «Блокировка», чтобы
  // длинные ссылки не растягивали строку на весь экран по высоте.
  if (!url || url.length <= maxLen) return url || "";
  try {
    const u = new URL(url);
    const path = u.pathname + u.search;
    const head = u.hostname;
    const keep = Math.max(maxLen - head.length - 1, 8);
    const shortPath = path.length > keep ? path.slice(0, keep) + "…" : path;
    return head + shortPath;
  } catch {
    return url.slice(0, maxLen - 1) + "…";
  }
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str ?? "";
  return d.innerHTML;
}

// ---------- «Постоянно блокируемые» — подсказки в результатах поиска по сайтам ----------
// Список составных зон, где «последние 2 части адреса» дают неверный
// базовый домен — тот же список, что и в backend/chronic_links.py
// (_MULTI_PART_TLDS), продублирован здесь: фронтенд не может импортировать
// Python-модуль напрямую, а вычислять базовый домен нужно уже в момент
// отрисовки результатов поиска, до отправки на сервер.
const SITE_SEARCH_MULTI_PART_TLDS = new Set([
  "co.uk", "org.uk", "net.uk", "ac.uk", "gov.uk",
  "co.jp", "ne.jp", "or.jp",
  "com.br", "com.au", "com.tr", "com.ua", "com.cn",
  "co.in", "co.nz", "co.za", "co.kr",
]);

function extractHostname(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function siteSearchBaseDomain(hostname) {
  // "s69.zapret.me" -> "zapret.me"; "example.co.uk" -> "example.co.uk"
  // (не "co.uk" — составная зона не считается доменом сама по себе).
  // Логика зеркалит backend/chronic_links.py::_base_domain — если там
  // поменяется список составных зон, нужно поправить и здесь тоже.
  if (!hostname) return "";
  hostname = hostname.toLowerCase().replace(/\.+$/, "");
  const parts = hostname.split(".");
  if (parts.length <= 2) return hostname;
  const lastTwo = parts.slice(-2).join(".");
  if (SITE_SEARCH_MULTI_PART_TLDS.has(lastTwo) && parts.length >= 3) return parts.slice(-3).join(".");
  return lastTwo;
}

function looksLikeMirrorSubdomain(hostname) {
  // "Похоже на сменщика" — эвристика по внешнему виду поддомена, не по
  // истории: короткая буква(-ы) + цифры (s69, s68, m12...) — типичная
  // нумерация у сайтов-зеркал. "shop2" не подходит (5 букв, не 1-2).
  if (!hostname) return false;
  const firstLabel = hostname.split(".")[0];
  return /^[a-z]{1,2}\d{1,3}$/i.test(firstLabel);
}

// ---------- bootstrap ----------
async function init() {
  await refreshAuth();
  await refreshSettings();
  await refreshTree();
  checkResumableBulkSearch();
}

async function checkResumableBulkSearch() {
  try {
    const info = await api("/api/works/run-all/resumable");
    if (!info.resumable) return;
    const proceed = confirm(
      `Обнаружен незавершённый массовый поиск (${info.scope_label}), прерванный ранее ` +
      `(например, перезапуском сервера) — готово ${info.done} из ${info.total}.\n\n` +
      `Продолжить с оставшихся ${info.remaining}?`
    );
    if (!proceed) {
      await api("/api/works/run-all/resumable", { method: "DELETE" });
      return;
    }
    const { started, count } = await api("/api/works/run-all/resume", { method: "POST" });
    started.forEach((s) => { state.activeJobs[s.work_id] = s.job_id; });
    ensureGlobalPoller();
    renderTree();
    updateStopAllVisibility();
    const statusEl = $("#runAllStatus");
    statusEl.textContent = `Продолжаю прерванный поиск — запущено ${count} произведений`;
    statusEl.classList.remove("hidden");
    setTimeout(() => statusEl.classList.add("hidden"), 6000);
  } catch (e) {
    // не критично — просто не предлагаем продолжение, если что-то пошло не так с самой проверкой
  }
}

async function refreshAuth() {
  try {
    const who = await api("/api/auth/whoami");
    state.role = who.role || null;
    if (who.role === "admin") checkCertStatus();
    $("#openClientReportBtn").classList.toggle("hidden", !(!who.enabled || who.role === "admin"));
    state.authEnabled = !!who.enabled;
    state.myGrants = [];
    state.canEditSites = true;  // если auth вообще выключен — все могут всё, как и везде в приложении
    if (who.enabled && who.username) {
      $("#userRow").classList.remove("hidden");
      $("#userNameLabel").textContent = who.username + (who.role ? ` (${ROLE_LABELS[who.role] || who.role})` : "");
      $("#myDocumentsBtn").classList.remove("hidden");
      if (who.role === "admin") {
        $("#adminMenuToggleBtn").classList.remove("hidden");
      } else {
        // admin и так видит всё — временные разрешения нужны только не-админам,
        // чтобы дерево авторов знало, каким конкретно авторам показывать
        // иконки 📄/🪪 (см. authorDocsVisible).
        try {
          state.myGrants = await api("/api/document-access-grants/mine");
        } catch (e) {
          // не критично — просто не покажем лишние иконки, если запрос не удался
        }
      }
      // Право редактировать справочник «Поиск по сайтам» — тоже нужно
      // знать явно (не только не-admin: admin и так видит canEditSites
      // = true через первую ветку ниже), чтобы показать/скрыть кнопки
      // «Изменить»/«Удалить»/«+Добавить сайт».
      if (who.role === "admin") {
        state.canEditSites = true;
      } else {
        try {
          const { has_access } = await api("/api/site-access-grants/mine");
          state.canEditSites = !!has_access;
        } catch (e) {
          state.canEditSites = false;
        }
      }
    }
  } catch (e) {
    // не критично, если недоступно — просто не показываем блок пользователя
  }
}

function authorDocsVisible(authorId) {
  if (!state.authEnabled || state.role === "admin") return true;
  return (state.myGrants || []).some((g) => g.scope === "all" || (g.scope === "author" && g.author_id === authorId));
}

const ROLE_LABELS = { admin: "администратор", editor: "редактор", viewer: "только просмотр" };

async function refreshSettings() {
  const s = await api("/api/settings");
  const el = $("#modeIndicator");
  const parts = [];
  parts.push(s.yandex_configured ? "Яндекс: подключён" : "Яндекс: демо");
  parts.push(s.google_configured ? "Google: подключён" : (s.google_demo_blocked ? "Google: не настроен" : "Google: демо"));
  state.settings = s;
  applySourceAvailability();
  el.textContent = parts.join(" · ");
  el.className = "status-pill " + (s.demo_mode ? "demo" : "live");
}

async function refreshTree(selectWorkId) {
  state.authors = await api("/api/authors");
  state.worksByAuthor = {};
  for (const a of state.authors) {
    state.worksByAuthor[a.id] = await api(`/api/authors/${a.id}/works`);
  }
  renderTree();
  if (selectWorkId) {
    selectWork(selectWorkId);
  } else if (state.activeWorkId) {
    selectWork(state.activeWorkId);
  }
}

function renderTree() {
  const tree = $("#tree");
  tree.innerHTML = "";
  state.authors.forEach((a) => {
    const group = document.createElement("div");
    group.className = "author-group";

    const collapsed = !!state.collapsed[a.id];
    const row = document.createElement("div");
    row.className = "author-row";
    const canSeeDocs = authorDocsVisible(a.id);
    row.innerHTML = `
      <span class="author-caret ${collapsed ? "collapsed" : ""}">▾</span>
      <span class="author-name">${escapeHtml(a.name)}</span>
      <span class="author-count">${a.works_count}</span>
      <span class="author-actions">
        <button class="icon-btn" data-action="run-author" title="Искать по всем активным произведениям этого автора">▶</button>
        ${canSeeDocs ? `<button class="icon-btn" data-action="docs-author" title="Документы автора (доверенности и т.п.) — admin или временное разрешение">📄</button>` : ""}
        ${canSeeDocs ? `<button class="icon-btn" data-action="personal-author" title="Личные данные автора (истца) для заявлений — admin или временное разрешение">🪪</button>` : ""}
        <button class="icon-btn" data-action="edit-author" title="Переименовать">✎</button>
        <button class="icon-btn" data-action="delete-author" title="Удалить автора и все его произведения">✕</button>
      </span>
    `;
    row.querySelector('[data-action="run-author"]').onclick = async (e) => {
      e.stopPropagation();
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const { started, count } = await api(`/api/authors/${a.id}/run-all`, { method: "POST" });
        started.forEach((s) => { state.activeJobs[s.work_id] = s.job_id; });
        ensureGlobalPoller();
        renderTree();
        if (!count) alert(`У автора «${a.name}» нет активных произведений для запуска`);
      } catch (err) {
        alert("Не удалось запустить поиск: " + err.message);
      } finally {
        btn.disabled = false;
      }
    };
    if (canSeeDocs) {
      row.querySelector('[data-action="docs-author"]').onclick = (e) => { e.stopPropagation(); openDocumentsModal(a); };
      row.querySelector('[data-action="personal-author"]').onclick = (e) => { e.stopPropagation(); openAuthorDataModal(a); };
    }
    row.querySelector('[data-action="edit-author"]').onclick = (e) => { e.stopPropagation(); openAuthorModal(a); };
    row.querySelector('[data-action="delete-author"]').onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`Удалить автора «${a.name}» и все его произведения? Отменить нельзя.`)) return;
      await api(`/api/authors/${a.id}`, { method: "DELETE" });
      if (state.activeAuthorId === a.id) { state.activeWorkId = null; state.activeAuthorId = null; }
      await refreshTree();
      if (!state.activeWorkId) showEmptyState();
    };
    row.onclick = () => {
      state.collapsed[a.id] = !state.collapsed[a.id];
      renderTree();
    };
    group.appendChild(row);

    if (!collapsed) {
      const works = state.worksByAuthor[a.id] || [];
      works.forEach((w) => {
        const item = document.createElement("div");
        const isRunning = !!state.activeJobs[w.id];
        item.className = "work-item" + (w.id === state.activeWorkId ? " active" : "") + (w.active ? "" : " inactive");
        item.innerHTML = `<span class="wi-dot"></span><span class="wi-title">${escapeHtml(w.title)}</span>${isRunning ? '<span class="wi-running" title="Идёт поиск">⏳</span>' : ""}`;
        item.onclick = () => selectWork(w.id);
        group.appendChild(item);
      });
      const addBtn = document.createElement("button");
      addBtn.className = "add-work-btn";
      addBtn.textContent = "+ произведение";
      addBtn.onclick = () => openWorkModal(null, a.id);
      group.appendChild(addBtn);
    }

    tree.appendChild(group);
  });
}

function findWork(workId) {
  for (const a of state.authors) {
    const w = (state.worksByAuthor[a.id] || []).find((x) => x.id === workId);
    if (w) return { work: w, author: a };
  }
  return null;
}

// Единый список всех «полноэкранных» разделов — раньше при добавлении
// нового раздела нужно было руками дописывать его в 8 разных мест по
// файлу (легко забыть один и получить два одновременно видимых раздела).
// Теперь достаточно добавить id сюда один раз.
const ALL_VIEW_IDS = [
  "emptyState", "workView", "siteSearchView", "blockingView", "archiveView",
  "auditLogView", "analyticsView", "accessView", "complaintSendLogView",
  "templatesView", "requisitesView", "documentAccessView", "accountingView",
];
function hideAllViews() {
  ALL_VIEW_IDS.forEach((id) => $("#" + id).classList.add("hidden"));
}

function showEmptyState() {
  hideAllViews();
  $("#emptyState").classList.remove("hidden");
}

const SOURCE_LABELS = { yandex: "Яндекс", google: "Google", avito: "Avito", telegram: "Telegram", duckduckgo: "DuckDuckGo",
  vk: "VK: записи", vk_video: "VK: видео", torrents: "Торренты" };

function selectWork(workId) {
  state.activeWorkId = workId;
  const found = findWork(workId);
  renderTree();
  if (!found) { showEmptyState(); return; }
  const { work: w, author: a } = found;
  state.activeAuthorId = a.id;

  hideAllViews();
  $("#workView").classList.remove("hidden");

  $("#pvAuthor").textContent = a.name;
  $("#pvName").textContent = w.title + (w.active ? "" : " (неактивно)");
  $("#pvQuery").textContent = Array.isArray(w.query) ? w.query.join(" | ") : w.query;
  $("#pvKeywords").textContent = w.keywords.length ? w.keywords.join(" | ") : "не заданы (фильтр отключён)";
  $("#pvNegKeywords").textContent = (w.negative_keywords || []).length ? w.negative_keywords.join(", ") : "нет";
  $("#pvPages").textContent = w.pages;
  const activeSources = Object.entries(w.sources || {}).filter(([, v]) => v).map(([k]) => SOURCE_LABELS[k]);
  $("#pvSources").textContent = activeSources.length ? activeSources.join(", ") : "Яндекс (по умолчанию)";
  $("#pvExtraBlocked").innerHTML = "Доп. исключения: <span>" + (w.extra_blocked_domains.length ? w.extra_blocked_domains.join(", ") : "нет") + "</span>";

  $("#runProgress").classList.add("hidden");
  $("#runBtn").classList.remove("hidden");
  $("#stopBtn").classList.add("hidden");
  $("#demoBanner").classList.add("hidden");
  $("#lastRunBlock").classList.add("hidden");

  // если по этому произведению поиск ещё идёт (запущен, пока пользователь был
  // в другом разделе) — сразу показать прогресс вместо пустого экрана
  const runningJobId = state.activeJobs[workId];
  if (runningJobId && state.jobCache[runningJobId]) {
    renderRunProgress(state.jobCache[runningJobId]);
  } else {
    // если поиск недавно завершился, пока пользователь был не здесь —
    // восстановить «снимок последнего запуска», а не заставлять запускать заново
    const cachedEntry = Object.values(state.jobCache).find((j) => j.workId === workId);
    if (cachedEntry && cachedEntry.status === "done" && cachedEntry.result) {
      if (cachedEntry.demo_mode) $("#demoBanner").classList.remove("hidden");
      renderSourceReport(cachedEntry.result.source_report);
      renderResults(cachedEntry.result, cachedEntry.id);
    }
  }

  loadSavedResults(workId);
}

async function loadSavedResults(workId) {
  const data = await api(`/api/works/${workId}/results`);
  if (state.activeWorkId !== workId) return; // пользователь уже переключился на другое произведение
  state.savedResults = data.items;
  state.savedIsFallback = data.is_fallback;
  renderSaved();
}

function renderSaved() {
  const body = $("#savedBody");
  body.innerHTML = "";
  $("#savedEmpty").classList.toggle("hidden", state.savedResults.length > 0);
  $("#savedFallbackWarning").classList.toggle("hidden", !state.savedIsFallback || state.savedResults.length === 0);

  state.savedResults.forEach((r) => {
    const tr = document.createElement("tr");
    if (r.already_in_blocking) tr.classList.add("row-already-blocked");
    tr.innerHTML = `
      <td><input type="checkbox" class="row-select-cb" data-url="${escapeHtml(r.url)}"></td>
      <td><span class="source-tag r-source">${escapeHtml(r.source || "Яндекс")}</span></td>
      <td><div class="r-title">${escapeHtml(r.title)}${r.already_in_blocking ? ' <span class="already-blocked-badge" title="Эта ссылка уже есть в таблице «Блокировка»">✓ уже добавлено</span>' : ""}</div><div class="r-desc">${escapeHtml(r.description)}</div></td>
      <td><a class="r-url" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a></td>
      <td>
        <div class="row-actions">
          <button class="row-btn" data-act="copy">Копировать</button>
          <button class="row-btn" data-act="copy-url" title="Скопировать только ссылку, без названия и описания">Копировать ссылку</button>
          ${r.already_in_blocking ? "" : '<button class="row-btn" data-act="block">→ В блокировку</button>'}
          <button class="row-btn danger" data-act="del">Удалить</button>
        </div>
      </td>
    `;
    tr.querySelector('[data-act="copy"]').onclick = (e) => copyRow(r, e.currentTarget);
    tr.querySelector('[data-act="copy-url"]').onclick = (e) => copyUrlOnly(r, e.currentTarget);
    tr.querySelector('[data-act="del"]').onclick = () => deleteSavedRow(r.id);
    const blockBtn = tr.querySelector('[data-act="block"]');
    if (blockBtn) blockBtn.onclick = (e) => {
      const found = findWork(state.activeWorkId);
      sendToBlocking(r, {
        author_name: found?.author?.name || "",
        work_title: found?.work?.title || "",
        work_id: state.activeWorkId,
      }, e.currentTarget);
    };
    body.appendChild(tr);
  });
}

async function sendToBlocking(r, meta, btn) {
  const payload = {
    author_name: meta.author_name || "",
    work_title: meta.work_title || "",
    work_id: meta.work_id || null,
    source: r.source || "",
    title: r.title,
    description: r.description || "",
    url: r.url,
  };
  try {
    await api("/api/blocking-cases", { method: "POST", body: JSON.stringify(payload) });
    if (btn) {
      btn.textContent = "В блокировке ✓";
      btn.disabled = true;
      btn.classList.add("copied");
    }
  } catch (e) {
    alert("Не удалось добавить в блокировку: " + e.message);
  }
}

function copyRow(r, btn) {
  copyText(`${r.title}\n${r.url}${r.description ? "\n" + r.description : ""}`, btn);
}

function copyUrlOnly(r, btn) {
  copyText(r.url, btn);
}

function copyText(text, btn, successLabel) {
  const done = () => {
    const old = btn.textContent;
    btn.textContent = successLabel || "Скопировано ✓";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = old; btn.classList.remove("copied"); }, 1500);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); done(); } catch (e) { /* noop */ }
  document.body.removeChild(ta);
}

function copySelectedUrls(tbodyId, btn) {
  const checked = document.querySelectorAll(`#${tbodyId} .row-select-cb:checked`);
  if (checked.length === 0) {
    alert("Сначала отметьте галочками нужные строки — чекбокс в самом начале каждой строки.");
    return;
  }
  const urls = [...checked].map((cb) => cb.dataset.url).join("\n");
  copyText(urls, btn, `Скопировано (${checked.length}) ✓`);
}

async function deleteSavedRow(rowId) {
  const workId = state.activeWorkId;
  await api(`/api/works/${workId}/results/${rowId}`, { method: "DELETE" });
  state.savedResults = state.savedResults.filter((r) => r.id !== rowId);
  renderSaved();
}

$("#addRowBtn").onclick = async () => {
  const url = $("#addUrl").value.trim();
  if (!url) { alert("Укажите ссылку"); return; }
  const payload = {
    url,
    title: $("#addTitle").value.trim(),
    description: $("#addDesc").value.trim(),
    source: "Добавлено вручную",
  };
  const saved = await api(`/api/works/${state.activeWorkId}/results`, { method: "POST", body: JSON.stringify(payload) });
  state.savedResults.push(saved);
  renderSaved();
  $("#addUrl").value = "";
  $("#addTitle").value = "";
  $("#addDesc").value = "";
};

$("#exportSavedCsvBtn").onclick = () => {
  window.location.href = `/api/works/${state.activeWorkId}/results/export.csv`;
};
$("#savedCopySelectedBtn").onclick = (e) => copySelectedUrls("savedBody", e.currentTarget);

$("#clearSavedBtn").onclick = async () => {
  if (!state.savedResults.length) return;
  if (!confirm(`Удалить все ${state.savedResults.length} сохранённых результатов по этому произведению? Отменить нельзя.`)) return;
  await api(`/api/works/${state.activeWorkId}/results`, { method: "DELETE" });
  state.savedResults = [];
  state.savedIsFallback = false;
  renderSaved();
};

$("#clearLastRunBtn").onclick = () => {
  // "Результаты последнего запуска" — это только снимок в памяти браузера
  // (сама выборка «Совпавшие с фильтром» уже сохранена выше отдельно),
  // поэтому очистка — чисто локальное действие, без обращения к серверу.
  state.currentPipeline = null;
  state.currentJobId = null;
  $("#lastRunBlock").classList.add("hidden");
};

async function addResultToSaved(r) {
  if (state.savedResults.some((s) => s.url === r.url)) return; // уже есть
  const payload = { url: r.url, title: r.title, description: r.description, source: r.source || "Яндекс" };
  const saved = await api(`/api/works/${state.activeWorkId}/results`, { method: "POST", body: JSON.stringify(payload) });
  state.savedResults.push(saved);
  renderSaved();
}

// ---------- run search ----------
// ---------- параллельный запуск поиска по нескольким произведениям сразу ----------
// state.activeJobs: workId -> jobId, пока задача ещё выполняется (running/queued)
// state.jobCache: jobId -> {workId, status, progress, result, error, demo_mode}
// Один общий опрос идёт постоянно в фоне и не зависит от того, какой раздел
// сейчас открыт — поэтому можно запустить поиск, переключиться на «Блокировку»
// или на другое произведение и запустить там ещё один поиск: оба продолжат
// работать параллельно, а бэкенд это уже поддерживает (многопоточный сервер).
state.activeJobs = {};
state.jobCache = {};
let globalPollerStarted = false;

function ensureGlobalPoller() {
  if (globalPollerStarted) return;
  globalPollerStarted = true;
  setInterval(pollAllActiveJobs, 1200);
}

async function pollAllActiveJobs() {
  const workIds = Object.keys(state.activeJobs);
  for (const workId of workIds) {
    const jobId = state.activeJobs[workId];
    let job;
    try {
      job = await api(`/api/jobs/${jobId}`);
    } catch (e) {
      continue; // временная сетевая ошибка — попробуем на следующем тике
    }
    state.jobCache[jobId] = { workId, ...job };

    if (job.status === "running" || job.status === "queued") {
      if (state.activeWorkId === workId) renderRunProgress(job);
      continue;
    }

    // задача завершилась (done, error или cancelled) — перестаём считать её «активной»
    delete state.activeJobs[workId];
    renderTree(); // убрать индикатор «идёт поиск» у этого произведения
    updateStopAllVisibility();

    if (state.activeWorkId === workId) {
      finishRunDisplay(job);
    }
    // если пользователь сейчас смотрит на другое произведение/раздел — ничего
    // на экране трогать не нужно: отфильтрованный результат уже сохранён на
    // сервере автоматически, а «снимок последнего запуска» подтянется сам,
    // когда он вернётся на это произведение (см. selectWork).
  }
}

function renderRunProgress(job) {
  $("#runProgress").classList.remove("hidden");
  $("#runBtn").classList.add("hidden");
  $("#stopBtn").classList.remove("hidden");
  const p = job.progress;
  const taskFrac = p.total_tasks ? (p.task - 1) / p.total_tasks : 0;
  const pageFrac = p.total_pages ? (p.page / p.total_pages) / (p.total_tasks || 1) : 0;
  const pct = Math.max(5, Math.round((taskFrac + pageFrac) * 100));
  $("#progressFill").style.width = pct + "%";
  $("#progressLabel").textContent = `Источник «${p.source || "…"}»: страница ${p.page} из ${p.total_pages} (задача ${p.task}/${p.total_tasks})`;
}

function finishRunDisplay(job) {
  $("#runProgress").classList.add("hidden");
  $("#runBtn").classList.remove("hidden");
  $("#stopBtn").classList.add("hidden");
  if (job.status === "cancelled") {
    // всё равно показываем то, что успело найтись до остановки — не пропадает бесследно
    if (job.result) renderResults(job.result, job.id);
    loadSavedResults(state.activeWorkId);
    return;
  }
  if (job.status === "error") {
    alert("Ошибка при поиске: " + job.error);
    return;
  }
  if (job.demo_mode) $("#demoBanner").classList.remove("hidden");
  renderSourceReport(job.result && job.result.source_report);
  renderResults(job.result, job.id);
  loadSavedResults(state.activeWorkId); // сервер уже сохранил новый список — подтягиваем его
}

$("#stopBtn").onclick = async () => {
  const jobId = state.activeJobs[state.activeWorkId];
  if (!jobId) return;
  $("#stopBtn").disabled = true;
  try {
    await api(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  } catch (e) {
    alert("Не удалось остановить поиск: " + e.message);
  } finally {
    $("#stopBtn").disabled = false;
  }
};

async function runActiveWork() {
  const found = findWork(state.activeWorkId);
  if (!found) return;
  const workId = found.work.id;

  $("#runProgress").classList.remove("hidden");
  $("#runBtn").classList.add("hidden");
  $("#stopBtn").classList.remove("hidden");
  $("#lastRunBlock").classList.add("hidden");
  $("#demoBanner").classList.add("hidden");
  $("#progressFill").style.width = "3%";
  $("#progressLabel").textContent = "Запуск поиска…";

  const { job_id } = await api(`/api/works/${workId}/run`, { method: "POST" });
  state.activeJobs[workId] = job_id;
  ensureGlobalPoller();
  renderTree(); // сразу показать индикатор «идёт поиск» у этого произведения
  updateStopAllVisibility();
}

function updateStopAllVisibility() {
  const hasActive = Object.keys(state.activeJobs).length > 0;
  $("#runAllBtn").classList.toggle("hidden", hasActive);
  $("#stopAllBtn").classList.toggle("hidden", !hasActive);
}

$("#stopAllBtn").onclick = async () => {
  $("#stopAllBtn").disabled = true;
  try {
    await api("/api/jobs/cancel-all", { method: "POST" });
  } catch (e) {
    alert("Не удалось остановить поиск: " + e.message);
  } finally {
    $("#stopAllBtn").disabled = false;
  }
};

$("#runAllBtn").onclick = async () => {
  const btn = $("#runAllBtn");
  btn.disabled = true;
  const oldLabel = btn.textContent;
  btn.textContent = "Запускаю…";
  try {
    const { started, count } = await api("/api/works/run-all", { method: "POST" });
    started.forEach((s) => { state.activeJobs[s.work_id] = s.job_id; });
    ensureGlobalPoller();
    renderTree(); // сразу показать индикаторы «идёт поиск» у всех запущенных
    updateStopAllVisibility();
    const statusEl = $("#runAllStatus");
    statusEl.textContent = count
      ? `Запущено произведений: ${count} — можно переключаться между разделами, поиск идёт в фоне`
      : "Нет активных произведений для запуска";
    statusEl.classList.remove("hidden");
    setTimeout(() => statusEl.classList.add("hidden"), 6000);
  } catch (e) {
    alert("Не удалось запустить массовый поиск: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = oldLabel;
  }
};

function renderResults(pipeline, jobId) {
  $("#lastRunBlock").classList.remove("hidden");
  $("#funnel").innerHTML = [
    ["Найдено", pipeline.raw_count],
    ["После исключения официалов", pipeline.after_domain_exclude],
    ["После фильтра по словам", pipeline.after_keyword_filter],
    ["Уникальных", pipeline.after_dedupe],
  ].map(([label, val]) => `<div class="funnel-step">${label}: <b>${val}</b></div>`).join("");

  state.currentPipeline = pipeline;
  state.currentJobId = jobId;
  state.currentScope = "filtered";
  document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.toggle("active", b.dataset.scope === "filtered"));
  renderTable("filtered");

  $("#sendTelegramBtn").onclick = async () => {
    try {
      await api(`/api/jobs/${jobId}/send-telegram`, { method: "POST" });
      alert("Отправлено в Telegram");
    } catch (e) {
      alert("Не удалось отправить: " + e.message);
    }
  };
  $("#lastRunCopySelectedBtn").onclick = (e) => copySelectedUrls("resultsBody", e.currentTarget);
}

function renderTable(scope) {
  const pipeline = state.currentPipeline;
  if (!pipeline) return;
  const results = scope === "all" ? pipeline.all_results : pipeline.results;

  const body = $("#resultsBody");
  body.innerHTML = "";
  $("#noResults").classList.toggle("hidden", results.length > 0);

  results.forEach((r) => {
    const alreadySaved = state.savedResults.some((s) => s.url === r.url);
    const tr = document.createElement("tr");
    if (r.already_in_blocking) tr.classList.add("row-already-blocked");
    tr.innerHTML = `
      <td><input type="checkbox" class="row-select-cb" data-url="${escapeHtml(r.url)}"></td>
      <td class="r-num">${r.position ?? ""}</td>
      <td><span class="source-tag r-source">${escapeHtml(r.source || "Яндекс")}</span></td>
      <td><div class="r-title">${escapeHtml(r.title)}${r.already_in_blocking ? ' <span class="already-blocked-badge" title="Эта ссылка уже есть в таблице «Блокировка»">✓ уже добавлено</span>' : ""}</div><div class="r-desc">${escapeHtml(r.description)}</div></td>
      <td><a class="r-url" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a></td>
      <td>
        <div class="row-actions">
          <button class="row-btn" data-act="copy">Копировать</button>
          <button class="row-btn" data-act="copy-url" title="Скопировать только ссылку, без названия и описания">Копировать ссылку</button>
          ${scope === "all" ? `<button class="row-btn" data-act="add" ${alreadySaved ? "disabled" : ""}>${alreadySaved ? "Уже сохранено" : "+ В сохранённые"}</button>` : ""}
          ${r.already_in_blocking ? "" : '<button class="row-btn" data-act="block">→ В блокировку</button>'}
        </div>
      </td>
    `;
    tr.querySelector('[data-act="copy"]').onclick = (e) => copyRow(r, e.currentTarget);
    tr.querySelector('[data-act="copy-url"]').onclick = (e) => copyUrlOnly(r, e.currentTarget);
    if (scope === "all" && !alreadySaved) {
      tr.querySelector('[data-act="add"]').onclick = async (e) => {
        await addResultToSaved(r);
        e.currentTarget.textContent = "Уже сохранено";
        e.currentTarget.disabled = true;
      };
    }
    const blockBtn2 = tr.querySelector('[data-act="block"]');
    if (blockBtn2) blockBtn2.onclick = (e) => {
      const found = findWork(state.activeWorkId);
      sendToBlocking(r, {
        author_name: found?.author?.name || "",
        work_title: found?.work?.title || "",
        work_id: state.activeWorkId,
      }, e.currentTarget);
    };
    body.appendChild(tr);
  });
}

document.querySelectorAll(".toggle-btn").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    state.currentScope = btn.dataset.scope;
    renderTable(state.currentScope);
  };
});

// ---------- author modal ----------
let editingAuthorId = null;

function openAuthorModal(author) {
  editingAuthorId = author ? author.id : null;
  $("#authorModalTitle").textContent = author ? "Переименовать автора" : "Новый автор";
  $("#aName").value = author?.name || "";
  $("#aReportPeriodStartDay").value = author?.report_period_start_day || 1;
  $("#authorModalOverlay").classList.remove("hidden");
}
$("#newAuthorBtn").onclick = () => openAuthorModal(null);
$("#cancelAuthorBtn").onclick = () => $("#authorModalOverlay").classList.add("hidden");
$("#saveAuthorBtn").onclick = async () => {
  const name = $("#aName").value.trim();
  if (!name) { alert("Введите имя автора"); return; }
  const startDay = parseInt($("#aReportPeriodStartDay").value, 10) || 1;
  if (startDay < 1 || startDay > 28) { alert("День начала отчётного периода — от 1 до 28"); return; }
  const payload = { name, report_period_start_day: startDay };
  if (editingAuthorId) {
    await api(`/api/authors/${editingAuthorId}`, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    await api("/api/authors", { method: "POST", body: JSON.stringify(payload) });
  }
  $("#authorModalOverlay").classList.add("hidden");
  await refreshTree();
};

// ---------- work modal ----------
let editingWorkId = null;

function populateAuthorSelect(selectedId) {
  const sel = $("#wAuthor");
  sel.innerHTML = state.authors.map((a) => `<option value="${a.id}" ${a.id === selectedId ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("");
}

function openWorkModal(work, presetAuthorId) {
  editingWorkId = work ? work.id : null;
  $("#workModalTitle").textContent = work ? "Изменить произведение" : "Новое произведение";
  populateAuthorSelect(work ? work.author_id : presetAuthorId);
  $("#wTitle").value = work?.title || "";
  $("#wQuery").value = work ? (Array.isArray(work.query) ? work.query.join("\n") : (work.query || "")) : "";
  $("#wKeywords").value = work ? work.keywords.join("\n") : "";
  $("#wNegKeywords").value = work ? (work.negative_keywords || []).join("\n") : "";
  $("#wPages").value = work?.pages || 7;
  $("#wExtraBlocked").value = work ? work.extra_blocked_domains.join("\n") : "";
  $("#wCustomerSite").value = work?.customer_site_url || "";
  $("#wActive").checked = work ? work.active !== false : true;
  const src = work?.sources || { yandex: true, google: false, avito: false, telegram: false, duckduckgo: false };
  $("#srcYandex").checked = !!src.yandex;
  $("#srcGoogle").checked = !!src.google;
  $("#srcAvito").checked = !!src.avito;
  $("#srcTelegram").checked = !!src.telegram;
  $("#srcDuckduckgo").checked = !!src.duckduckgo;
  $("#srcVk").checked = !!src.vk;
  $("#srcVkVideo").checked = !!src.vk_video;
  $("#srcTorrents").checked = !!src.torrents;
  applySourceAvailability();
  $("#workModalOverlay").classList.remove("hidden");
}
$("#cancelWorkBtn").onclick = () => $("#workModalOverlay").classList.add("hidden");
$("#saveWorkBtn").onclick = async () => {
  const payload = {
    author_id: $("#wAuthor").value,
    title: $("#wTitle").value.trim(),
    query: $("#wQuery").value.split("\n").map((s) => s.trim()).filter(Boolean),
    keywords: $("#wKeywords").value.split("\n").map((s) => s.trim()).filter(Boolean),
    negative_keywords: $("#wNegKeywords").value.split("\n").map((s) => s.trim()).filter(Boolean),
    pages: parseInt($("#wPages").value, 10) || 7,
    extra_blocked_domains: $("#wExtraBlocked").value.split("\n").map((s) => s.trim()).filter(Boolean),
    customer_site_url: $("#wCustomerSite").value.trim(),
    active: $("#wActive").checked,
    sources: {
      yandex: $("#srcYandex").checked,
      google: $("#srcGoogle").checked,
      avito: $("#srcAvito").checked,
      telegram: $("#srcTelegram").checked,
      duckduckgo: $("#srcDuckduckgo").checked,
      vk: $("#srcVk").checked,
      vk_video: $("#srcVkVideo").checked,
      torrents: $("#srcTorrents").checked,
    },
  };
  if (!payload.title || !payload.query.length) { alert("Заполните название и поисковый запрос"); return; }
  if (!Object.values(payload.sources).some(Boolean)) { alert("Выберите хотя бы один источник поиска"); return; }

  let saved;
  if (editingWorkId) {
    saved = await api(`/api/works/${editingWorkId}`, { method: "PUT", body: JSON.stringify(payload) });
  } else {
    saved = await api("/api/works", { method: "POST", body: JSON.stringify(payload) });
  }
  $("#workModalOverlay").classList.add("hidden");
  await refreshTree(saved.id);
};

$("#editWorkBtn").onclick = () => {
  const found = findWork(state.activeWorkId);
  if (found) openWorkModal(found.work, found.author.id);
};
$("#deleteWorkBtn").onclick = async () => {
  if (!confirm("Удалить это произведение? Отменить нельзя.")) return;
  await api(`/api/works/${state.activeWorkId}`, { method: "DELETE" });
  state.activeWorkId = null;
  await refreshTree();
  showEmptyState();
};
$("#runBtn").onclick = runActiveWork;

// ---------- settings modal (только общий блок-лист — остальное переехало в разделы администрирования) ----------
async function openSettingsModal() {
  const [settings, blocklist] = await Promise.all([api("/api/settings"), api("/api/blocklist")]);
  $("#settingsStatus").innerHTML = [
    ["Yandex Search API", settings.yandex_configured],
    ["Google Custom Search", settings.google_configured],
    ["Telegram", settings.telegram_configured],
  ].map(([label, ok]) => `<span class="status-badge ${ok ? "ok" : "off"}">${label}: ${ok ? "подключено" : "не настроено"}</span>`).join("")
    + ` <span class="status-badge ${settings.duckduckgo_serpapi_fallback_configured ? "ok" : "off"}">DuckDuckGo (резерв SerpApi): ${settings.duckduckgo_serpapi_fallback_configured ? "подключено" : "не настроено, но не обязательно — DuckDuckGo доступен и без него"}</span>`
    + [["VK: записи", settings.vk_configured], ["VK: видео", settings.vk_video_configured], ["Торренты (агрегатор)", settings.torrents_configured]]
      .map(([label, ok]) => ` <span class="status-badge ${ok ? "ok" : "off"}">${label}: ${ok ? "подключено" : "не настроено"}</span>`).join("")
    + ` <span class="status-badge ok">Выдача Яндекса: ${({ html: "HTML (как раньше)", compare: "сравнение HTML и XML", xml: "XML" })[settings.yandex_response_format] || settings.yandex_response_format}</span>`
    + `<div id="yandexCompareSummary" class="hint-text"></div>`;
  if (settings.yandex_response_format !== "html" && state.role === "admin") {
    api("/api/admin/yandex-compare").then((c) => {
      const el = $("#yandexCompareSummary");
      if (!el) return;
      el.textContent = c.pages_compared
        ? `Сравнение Яндекса: страниц ${c.pages_compared}; XML нашёл не меньше HTML на ${c.xml_not_worse} из ${c.pages_compared - c.xml_errors}; всего ссылок HTML ${c.html_total}, XML ${c.xml_total}; только в HTML ${c.urls_only_in_html}, только в XML ${c.urls_only_in_xml}; ошибок XML ${c.xml_errors}.`
        : "Сравнение Яндекса: данных пока нет — запустите несколько поисков.";
    }).catch(() => {});
  }
  $("#fBlocklist").value = blocklist.join("\n");
  $("#settingsModalOverlay").classList.remove("hidden");
}
$("#settingsBtn").onclick = openSettingsModal;
$("#closeSettingsBtn").onclick = () => $("#settingsModalOverlay").classList.add("hidden");
$("#saveBlocklistBtn").onclick = async () => {
  const domains = $("#fBlocklist").value.split("\n").map((s) => s.trim()).filter(Boolean);
  const saved = await api("/api/blocklist", { method: "POST", body: JSON.stringify({ domains }) });
  $("#fBlocklist").value = saved.join("\n");
  $("#settingsModalOverlay").classList.add("hidden");
};

// ---------- раздел «Шаблоны» ----------
async function showTemplatesView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#templatesView").classList.remove("hidden");
  const claim = await api("/api/settings/complaint-template");
  $("#tplClaimSubject").value = claim.subject;
  $("#tplClaimBody").value = claim.body;
  $("#tplClaimCustomBadge").classList.toggle("hidden", !claim.is_custom);
  await loadCustomTemplates();
}
$("#templatesBtn").onclick = showTemplatesView;

async function loadCustomTemplates() {
  const templates = await api("/api/custom-templates");
  const body = $("#customTemplatesBody");
  body.innerHTML = "";
  $("#customTemplatesEmpty").classList.toggle("hidden", templates.length > 0);
  templates.forEach((t) => {
    const tr = document.createElement("tr");
    const shortBody = t.body.length > 80 ? t.body.slice(0, 80) + "…" : t.body;
    tr.innerHTML = `
      <td><b>${escapeHtml(t.name)}</b></td>
      <td>${escapeHtml(t.subject || "—")}</td>
      <td class="r-desc" title="${escapeHtml(t.body)}">${escapeHtml(shortBody)}</td>
      <td>
        <button class="row-btn" data-act="copy">Скопировать</button>
        <button class="row-btn danger" data-act="del">Удалить</button>
      </td>
    `;
    tr.querySelector('[data-act="copy"]').onclick = async () => {
      const text = t.subject ? `${t.subject}\n\n${t.body}` : t.body;
      try {
        await navigator.clipboard.writeText(text);
        alert(`Скопировано: «${t.name}»`);
      } catch (err) {
        alert("Не удалось скопировать автоматически — выделите текст руками:\n\n" + text);
      }
    };
    tr.querySelector('[data-act="del"]').onclick = async () => {
      if (!confirm(`Удалить шаблон «${t.name}»? Отменить нельзя.`)) return;
      await api(`/api/custom-templates/${t.id}`, { method: "DELETE" });
      await loadCustomTemplates();
    };
    body.appendChild(tr);
  });
}

$("#customTemplateForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#ctName").value.trim();
  const subject = $("#ctSubject").value.trim();
  const bodyText = $("#ctBody").value.trim();
  if (!name || !bodyText) { alert("Заполните название и текст."); return; }
  const btn = $("#ctAddBtn");
  btn.disabled = true;
  try {
    await api("/api/custom-templates", { method: "POST", body: JSON.stringify({ name, subject, body: bodyText }) });
    $("#customTemplateForm").reset();
    await loadCustomTemplates();
  } catch (err) {
    alert("Не удалось добавить шаблон: " + err.message);
  } finally {
    btn.disabled = false;
  }
});

$("#tplClaimSaveBtn").onclick = async () => {
  const subject = $("#tplClaimSubject").value.trim();
  const body = $("#tplClaimBody").value.trim();
  if (!subject || !body) { alert("Тема и текст письма не могут быть пустыми."); return; }
  try {
    await api("/api/settings/complaint-template", { method: "PUT", body: JSON.stringify({ subject, body }) });
    $("#tplClaimCustomBadge").classList.remove("hidden");
    alert("Шаблон претензии сохранён.");
  } catch (err) {
    alert("Не удалось сохранить шаблон: " + err.message);
  }
};
$("#tplClaimResetBtn").onclick = async () => {
  if (!confirm("Вернуть шаблон претензии к тексту по умолчанию? Ваш текущий вариант будет забыт.")) return;
  const reset = await api("/api/settings/complaint-template", { method: "DELETE" });
  $("#tplClaimSubject").value = reset.subject;
  $("#tplClaimBody").value = reset.body;
  $("#tplClaimCustomBadge").classList.add("hidden");
};

// ---------- раздел «Заказчик и реквизиты» ----------
const ENTITY_TYPE_LABELS = { individual: "Физическое лицо", individual_entrepreneur: "ИП", organization: "Юридическое лицо" };

async function showRequisitesView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#requisitesView").classList.remove("hidden");
  const [letterhead, authors] = await Promise.all([api("/api/settings/firm-letterhead"), api("/api/authors")]);
  $("#reqFirmName").value = letterhead.name || "";
  $("#reqFirmEmail").value = letterhead.email || "";
  $("#reqFirmPhone").value = letterhead.phone || "";
  $("#reqFirmAddress").value = letterhead.address || "";

  const body = $("#requisitesAuthorsBody");
  body.innerHTML = "";
  for (const a of authors) {
    // Реквизиты и договорные условия теперь в защищённой записи
    // author_personal_data, не на самом объекте автора — запрашиваем
    // отдельно на каждую строку.
    let fields = {};
    try {
      fields = await api(`/api/authors/${a.id}/personal-data`);
    } catch (e) {
      // недостаточно прав или данных ещё нет — просто покажем пустую строку
    }
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${escapeHtml(a.name)}</b></td>
      <td>${ENTITY_TYPE_LABELS[fields.entity_type] || "Физическое лицо"}</td>
      <td>${escapeHtml(fields.customer_name || "—")}</td>
      <td>${escapeHtml(fields.contract_number || "—")}</td>
      <td>${fields.contract_date ? formatIsoDateRu(fields.contract_date) : "—"}</td>
      <td>${escapeHtml(fields.monthly_fee || "—")}</td>
      <td>
        <button class="row-btn" data-act="edit">✎ Изменить</button>
        <button class="row-btn" data-act="docs">📄 Документы</button>
      </td>
    `;
    tr.querySelector('[data-act="edit"]').onclick = () => openAuthorDataModal(a);
    tr.querySelector('[data-act="docs"]').onclick = () => openDocumentsModal(a);
    body.appendChild(tr);
  }
}
$("#requisitesBtn").onclick = showRequisitesView;
$("#reqFirmSaveBtn").onclick = async () => {
  try {
    await api("/api/settings/firm-letterhead", {
      method: "PUT",
      body: JSON.stringify({
        name: $("#reqFirmName").value.trim(),
        email: $("#reqFirmEmail").value.trim(),
        phone: $("#reqFirmPhone").value.trim(),
        address: $("#reqFirmAddress").value.trim(),
      }),
    });
    alert("Реквизиты юрфирмы сохранены — теперь будут подставляться в шапку акта выполненных работ.");
  } catch (err) {
    alert("Не удалось сохранить: " + err.message);
  }
};

// ---------- раздел «Доступ к документам» (временные разрешения) ----------
async function showDocumentAccessView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#documentAccessView").classList.remove("hidden");
  const [users, authors] = await Promise.all([api("/api/users"), api("/api/authors")]);
  const employeeSelect = $("#daEmployee");
  employeeSelect.innerHTML = users.map((u) => `<option value="${escapeHtml(u.username)}">${escapeHtml(u.username)} (${escapeHtml(ROLE_LABELS[u.role] || u.role)})</option>`).join("");
  const authorSelect = $("#daAuthor");
  authorSelect.innerHTML = authors.map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join("");
  await loadDocumentAccessGrants();
}
$("#documentAccessBtn").onclick = showDocumentAccessView;

$("#daScope").addEventListener("change", () => {
  $("#daAuthorLabel").classList.toggle("hidden", $("#daScope").value !== "author");
});
$("#daDurationPreset").addEventListener("change", () => {
  $("#daCustomDateLabel").classList.toggle("hidden", $("#daDurationPreset").value !== "custom");
});

async function loadDocumentAccessGrants() {
  const grants = await api("/api/document-access-grants");
  const now = Date.now() / 1000;
  const active = grants.filter((g) => !g.revoked && (!g.expires_at || g.expires_at > now));
  const body = $("#documentAccessBody");
  body.innerHTML = "";
  $("#documentAccessEmpty").classList.toggle("hidden", active.length > 0);
  active.forEach((g) => {
    const tr = document.createElement("tr");
    const scopeLabel = g.scope === "all" ? "Все авторы" : (g.author_name || g.author_id);
    tr.innerHTML = `
      <td><b>${escapeHtml(g.username)}</b></td>
      <td>${escapeHtml(scopeLabel)}</td>
      <td>${escapeHtml(g.granted_by || "—")}</td>
      <td>${new Date(g.expires_at * 1000).toLocaleString("ru-RU")}</td>
      <td><button class="row-btn danger" data-act="revoke">Отозвать</button></td>
    `;
    tr.querySelector('[data-act="revoke"]').onclick = async () => {
      if (!confirm(`Отозвать разрешение у «${g.username}»?`)) return;
      await api(`/api/document-access-grants/${g.id}`, { method: "DELETE" });
      await loadDocumentAccessGrants();
    };
    body.appendChild(tr);
  });
}

$("#daGrantBtn").onclick = async () => {
  const username = $("#daEmployee").value;
  const scope = $("#daScope").value;
  const authorId = scope === "author" ? $("#daAuthor").value : null;
  const preset = $("#daDurationPreset").value;
  const payload = { username, scope, author_id: authorId };
  if (preset === "custom") {
    const customDate = $("#daCustomDate").value;
    if (!customDate) { alert("Укажите дату окончания."); return; }
    payload.expires_at = customDate;
  } else {
    payload.duration_days = Number(preset);
  }
  try {
    await api("/api/document-access-grants", { method: "POST", body: JSON.stringify(payload) });
    await loadDocumentAccessGrants();
  } catch (err) {
    alert("Не удалось выдать разрешение: " + err.message);
  }
};

// ---------- раздел «Бухгалтерия» (заглушка) ----------
$("#accountingBtn").onclick = () => {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#accountingView").classList.remove("hidden");
};

// ---------- отдельный раздел: поиск по сайтам ----------
state.sites = [];
let editingSiteId = null;

function showSiteSearchView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#siteSearchView").classList.remove("hidden");
  // раньше тут всегда прятался прогресс и ошибки при каждом заходе на
  // страницу — из-за этого казалось, что поиск «остановился», если уйти
  // в другой раздел и вернуться: сам поиск всё это время продолжался на
  // сервере и опрос статуса (pollSiteSearchJob) не прекращался, просто
  // индикатор прогресса принудительно скрывался. Прячем его теперь только
  // если поиск и правда не идёт — иначе оставляем как есть, интервал сам
  // обновит цифры на следующем тике.
  if (!currentSiteSearchJobId) {
    $("#siteSearchProgress").classList.add("hidden");
    $("#siteSearchErrors").classList.add("hidden");
    // Если в этой вкладке браузера ещё не было результатов «Поиск по
    // сайтам» (например, приложение только что открыли/перезапустили) —
    // подгружаем последний сохранённый на сервере результат, чтобы он не
    // выглядел пропавшим. Загружаем один раз за сессию вкладки — дальше
    // новый запуск поиска сам заменит его актуальным.
    if (state.lastSiteResults === undefined) {
      restoreLastSiteSearchResults();
    }
  }
  loadSiteDirectory();
  populateSiteSearchAttachWorkSelect();
  // Нужны для подсказок «уже постоянно блокируется у [автора]» в
  // результатах поиска ниже — лёгкий запрос, не блокирует остальную
  // загрузку раздела.
  api("/api/chronic-domains").then((groups) => {
    state.chronicGroups = groups;
    if (state.lastSiteResults) renderSiteResults(state.lastSiteResults);
  }).catch(() => {});
}

async function restoreLastSiteSearchResults() {
  state.lastSiteResults = null; // помечаем «уже пытались» — не пытаемся повторно при каждом заходе в раздел
  let saved;
  try {
    saved = await api("/api/sites/last-search-results");
  } catch (e) {
    return; // тихо — это фоновое восстановление, не критичная операция
  }
  if (!saved || !saved.result) return;
  const data = saved.result;
  renderSiteRedirects(data.redirects || []);
  renderSiteReport(data);
  renderSiteResults(data.results || []);
  const savedDate = saved.saved_at ? new Date(saved.saved_at * 1000).toLocaleString("ru-RU") : "";
  $("#siteSearchErrors").classList.remove("hidden");
  $("#siteSearchErrors").textContent = savedDate
    ? `Показаны результаты последнего поиска (сохранены на сервере, ${savedDate}) — запустите поиск заново для актуальных данных.`
    : "Показаны результаты последнего поиска, сохранённые на сервере — запустите поиск заново для актуальных данных.";
}

function populateSiteSearchAttachWorkSelect() {
  const sel = $("#siteSearchAttachWork");
  const prevValue = sel.value;
  const options = ['<option value="">— не выбрано —</option>'];
  state.authors.forEach((a) => {
    const works = state.worksByAuthor[a.id] || [];
    works.forEach((w) => {
      options.push(`<option value="${w.id}">${escapeHtml(a.name)} — ${escapeHtml(w.title)}</option>`);
    });
  });
  sel.innerHTML = options.join("");
  if ([...sel.options].some((o) => o.value === prevValue)) sel.value = prevValue;
}
$("#siteSearchAttachWork").onchange = () => {
  // Бейдж «уже постоянно блокируется у автора» (см. renderSiteResults)
  // зависит от того, какой автор сейчас выбран здесь — перерисовываем
  // уже показанные результаты, чтобы бейдж пересчитался под нового автора,
  // не дожидаясь нового поиска.
  if (state.lastSiteResults) renderSiteResults(state.lastSiteResults);
};

// ---------- отдельный раздел: блокировка ----------
state.blockingCases = [];
// Группы (автор, произведение, домен) из /api/chronic-domains — раздел
// "Постоянно блокируемые ссылки" убран 17.09.2026 (эти дела теперь
// обычные строки "Блокировки"), но сами группы по-прежнему нужны:
// используются для бейджа "⭐ уже хронический" в "Поиск по сайтам" (см.
// renderSiteResults) и на сервере — для авто-добавления домена в
// справочник сайтов (backend/app.py, _maybe_add_chronic_domain_to_site_directory).
state.chronicGroups = [];

function showBlockingView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#blockingView").classList.remove("hidden");
  loadBlockingCases();
}

// ---------- отдельный раздел: журнал действий ----------
function showAuditLogView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#auditLogView").classList.remove("hidden");
  loadAuditLog();
}

async function loadAuditLog() {
  const entries = await api("/api/audit-log?limit=300");
  const body = $("#auditLogBody");
  body.innerHTML = "";
  $("#auditLogEmpty").classList.toggle("hidden", entries.length > 0);
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    const dt = new Date(e.ts * 1000).toLocaleString("ru-RU");
    tr.innerHTML = `
      <td class="r-num">${dt}</td>
      <td><b>${escapeHtml(e.username)}</b></td>
      <td>${escapeHtml(e.action)}</td>
      <td class="r-desc">${escapeHtml(e.details || "")}</td>
    `;
    body.appendChild(tr);
  });
}

$("#auditLogBtn").onclick = showAuditLogView;

// ---------- отдельный раздел: журнал отправок (только admin) ----------
function showComplaintSendLogView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#complaintSendLogView").classList.remove("hidden");
  loadComplaintSendLog();
}

async function loadComplaintSendLog() {
  const entries = await api("/api/complaint-send-log?limit=500");
  const body = $("#complaintSendLogBody");
  body.innerHTML = "";
  $("#complaintSendLogEmpty").classList.toggle("hidden", entries.length > 0);
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    const dt = new Date(e.ts * 1000).toLocaleString("ru-RU");
    const who = [e.author_name, e.work_title].filter(Boolean).join(" — ") || "—";
    tr.innerHTML = `
      <td class="r-num">${dt}</td>
      <td><b>${escapeHtml(e.username)}</b></td>
      <td>${escapeHtml(e.type_label || e.type)}</td>
      <td>${escapeHtml(who)}</td>
      <td class="r-desc">${e.url ? `<a href="${escapeHtml(e.url)}" target="_blank" rel="noopener">${escapeHtml(e.url)}</a>` : "—"}</td>
      <td class="r-num">${escapeHtml(e.date_value || "—")}</td>
      <td class="r-num">${escapeHtml(e.channel || "—")}</td>
    `;
    body.appendChild(tr);
  });
}

$("#complaintSendLogBtn").onclick = showComplaintSendLogView;

// ---------- отдельный раздел: аналитика (только admin) ----------
function showAnalyticsView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#analyticsView").classList.remove("hidden");
  loadAnalytics();
}

async function loadAnalytics() {
  const months = $("#analyticsMonthsSelect").value;
  const data = await api(`/api/analytics/summary?months=${months}`);

  renderAnalyticsBarChart("analyticsDetectedChart", data.detected.months, [
    { label: "Обнаружено", values: data.detected.counts, color: "var(--gold)" },
  ]);
  $("#analyticsDetectedTotal").textContent = data.detected.total_all_time;
  renderAnalyticsEditTable("analyticsDetectedEditTable", "detected", data.detected.months, data.detected.counts, data.detected.overridden);
  const domainsBody = $("#analyticsTopDomainsTable tbody");
  domainsBody.innerHTML = data.detected.top_domains.length
    ? data.detected.top_domains.map((d) => `<tr><td>${escapeHtml(d.domain)}</td><td>${d.count}</td></tr>`).join("")
    : `<tr><td colspan="2" class="hint-text">Пока нет данных</td></tr>`;

  renderAnalyticsBarChart("analyticsBlockedChart", data.blocked.months, [
    { label: "Заблокировано", values: data.blocked.counts, color: "var(--success)" },
  ]);
  $("#analyticsBlockedTotal").textContent = data.blocked.total_blocked_all_time;
  renderAnalyticsEditTable("analyticsBlockedEditTable", "blocked", data.blocked.months, data.blocked.counts, data.blocked.overridden);
  const statusBody = $("#analyticsStatusTable tbody");
  const statusEntries = Object.entries(data.blocked.status_breakdown).filter(([, n]) => n > 0);
  statusBody.innerHTML = statusEntries.length
    ? statusEntries.map(([status, n]) => `<tr><td>${escapeHtml(status)}</td><td>${n}</td></tr>`).join("")
    : `<tr><td colspan="2" class="hint-text">Пока нет данных</td></tr>`;

  renderAnalyticsBarChart("analyticsDynamicsChart", data.dynamics.months, [
    { label: "Обнаружено", values: data.dynamics.detected_counts, color: "var(--gold)" },
    { label: "Заблокировано", values: data.dynamics.blocked_counts, color: "var(--success)" },
  ]);
  if (data.dynamics.median_days_to_block === null) {
    $("#analyticsMedianDelay").textContent = "—";
    $("#analyticsMedianDelayCaption").textContent = "пока недостаточно данных (нужны дела, у которых известны и дата добавления, и дата блокировки)";
  } else {
    $("#analyticsMedianDelay").textContent = data.dynamics.median_days_to_block;
    $("#analyticsMedianDelayCaption").textContent = `медианное число дней от добавления ссылки до фактической блокировки — по ${data.dynamics.cases_with_known_delay} делам, где известны обе даты`;
  }
}

function renderAnalyticsBarChart(containerId, months, series) {
  // Простые столбчатые диаграммы на чистом SVG — без внешних библиотек
  // (в проекте их нет вообще, сознательно, чтобы не тянуть CDN-зависимость
  // на сервер, который может быть развёрнут без доступа в интернет).
  const container = $(`#${containerId}`);
  const width = 700, height = 220, padding = 32, labelHeight = 24;
  const chartHeight = height - padding - labelHeight;
  const maxValue = Math.max(1, ...series.flatMap((s) => s.values));
  const groupWidth = (width - padding * 2) / months.length;
  const barGap = 4;
  const barWidth = (groupWidth - barGap * (series.length + 1)) / series.length;

  let bars = "";
  months.forEach((month, i) => {
    const groupX = padding + i * groupWidth;
    series.forEach((s, si) => {
      const value = s.values[i] || 0;
      const barHeight = (value / maxValue) * chartHeight;
      const x = groupX + barGap + si * (barWidth + barGap);
      const y = chartHeight - barHeight + padding / 2;
      bars += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" fill="${s.color}" rx="2">
        <title>${escapeHtml(s.label)}, ${month}: ${value}</title>
      </rect>`;
      if (value > 0) {
        bars += `<text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="#666">${value}</text>`;
      }
    });
    const monthLabel = month.slice(2).replace("-", ".");  // "2026-08" -> "26.08"
    bars += `<text x="${(groupX + groupWidth / 2).toFixed(1)}" y="${height - 6}" text-anchor="middle" font-size="10" fill="#888">${monthLabel}</text>`;
  });

  const legend = series.length > 1
    ? series.map((s, i) => `<span class="analytics-legend-item"><span class="analytics-legend-dot" style="background:${s.color}"></span>${escapeHtml(s.label)}</span>`).join("")
    : "";

  container.innerHTML = `
    ${legend ? `<div class="analytics-legend">${legend}</div>` : ""}
    <svg viewBox="0 0 ${width} ${height}" class="analytics-svg">${bars}</svg>
  `;
}

function renderAnalyticsEditTable(tableId, metric, months, values, overridden) {
  const body = $(`#${tableId} tbody`);
  body.innerHTML = "";
  months.forEach((month, i) => {
    const isOverridden = overridden && overridden[i];
    const tr = document.createElement("tr");
    if (isOverridden) tr.classList.add("analytics-row-overridden");
    tr.innerHTML = `
      <td>${month}${isOverridden ? ' <span class="analytics-override-badge" title="Значение поправлено вручную">✎ поправлено</span>' : ""}</td>
      <td><input type="number" min="0" step="1" class="analytics-value-input" value="${values[i]}"></td>
      <td>${isOverridden ? '<button class="row-btn" data-act="reset" title="Вернуть автоматически посчитанное значение">↺</button>' : ""}</td>
    `;
    const input = tr.querySelector("input");
    input.onchange = async () => {
      const value = parseInt(input.value, 10);
      if (Number.isNaN(value) || value < 0) {
        alert("Значение должно быть целым числом не меньше нуля.");
        input.value = values[i];
        return;
      }
      await api("/api/analytics/overrides", {
        method: "PUT",
        body: JSON.stringify({ metric, month, value }),
      });
      await loadAnalytics();
    };
    const resetBtn = tr.querySelector('[data-act="reset"]');
    if (resetBtn) {
      resetBtn.onclick = async () => {
        await api("/api/analytics/overrides", {
          method: "PUT",
          body: JSON.stringify({ metric, month, value: null }),
        });
        await loadAnalytics();
      };
    }
    body.appendChild(tr);
  });
}

$("#analyticsBtn").onclick = showAnalyticsView;
$("#analyticsMonthsSelect").onchange = loadAnalytics;
$("#analyticsBuildReportBtn").onclick = () => {
  const months = $("#analyticsMonthsSelect").value;
  window.open(`/api/analytics/export.xlsx?months=${months}`, "_blank");
};

// ---------- отдельный раздел: доступ (пользователи и приглашения, только admin) ----------
function showAccessView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#accessView").classList.remove("hidden");
  loadUsers();
  loadInvites();
}

async function loadUsers() {
  const users = await api("/api/users");
  const body = $("#usersBody");
  body.innerHTML = "";
  const myUsername = $("#userNameLabel").textContent.split(" (")[0];
  users.forEach((u) => {
    const tr = document.createElement("tr");
    const created = u.created_at ? new Date(u.created_at * 1000).toLocaleDateString("ru-RU") : "—";
    const isSelf = u.username === myUsername;
    tr.innerHTML = `
      <td><b>${escapeHtml(u.username)}</b>${isSelf ? " <span class=\"hint-text\" style=\"display:inline\">(это вы)</span>" : ""}</td>
      <td>
        <select class="blocking-status-select" data-user-id="${u.id}" ${isSelf || u.role === "admin" ? "disabled" : ""}>
          <option value="admin" ${u.role === "admin" ? "selected" : ""}>Администратор</option>
          <option value="editor" ${u.role === "editor" ? "selected" : ""}>Редактор</option>
          <option value="viewer" ${u.role === "viewer" ? "selected" : ""}>Только просмотр</option>
        </select>
      </td>
      <td class="r-num">${created}</td>
      <td>${isSelf ? "" : `<button class="row-btn danger" data-act="del">Отозвать доступ</button>`}</td>
    `;
    const sel = tr.querySelector("select");
    if (!isSelf) {
      sel.addEventListener("change", async () => {
        try {
          await api(`/api/users/${u.id}`, { method: "PUT", body: JSON.stringify({ role: sel.value }) });
          await loadUsers();
        } catch (e) {
          alert("Не удалось изменить роль: " + e.message);
          await loadUsers();
        }
      });
      tr.querySelector('[data-act="del"]').onclick = async () => {
        if (!confirm(`Отозвать доступ у «${u.username}»? Отменить нельзя.`)) return;
        try {
          await api(`/api/users/${u.id}`, { method: "DELETE" });
          await loadUsers();
        } catch (e) {
          alert("Не удалось отозвать доступ: " + e.message);
        }
      };
    }
    body.appendChild(tr);
  });
}

async function loadInvites() {
  const invites = await api("/api/invites");
  const body = $("#invitesBody");
  body.innerHTML = "";
  $("#invitesEmpty").classList.toggle("hidden", invites.length > 0);
  invites.forEach((inv) => {
    const tr = document.createElement("tr");
    const expires = new Date(inv.expires_at * 1000).toLocaleDateString("ru-RU");
    const fullUrl = window.location.origin + "/join?token=" + inv.token;
    tr.innerHTML = `
      <td>${ROLE_LABELS[inv.role] || inv.role}</td>
      <td><code style="font-size:11px;">${escapeHtml(fullUrl)}</code></td>
      <td class="r-num">${expires}</td>
      <td>
        <div class="row-actions">
          <button class="row-btn" data-act="copy">Копировать</button>
          <button class="row-btn danger" data-act="revoke">Отозвать</button>
        </div>
      </td>
    `;
    tr.querySelector('[data-act="copy"]').onclick = (e) => {
      navigator.clipboard.writeText(fullUrl).then(() => {
        const btn = e.currentTarget;
        const old = btn.textContent;
        btn.textContent = "Скопировано ✓";
        setTimeout(() => (btn.textContent = old), 1200);
      });
    };
    tr.querySelector('[data-act="revoke"]').onclick = async () => {
      if (!confirm("Отозвать эту ссылку-приглашение?")) return;
      await api(`/api/invites/${inv.token}`, { method: "DELETE" });
      await loadInvites();
    };
    body.appendChild(tr);
  });
}

$("#createInviteBtn").onclick = async () => {
  const role = $("#newInviteRole").value;
  try {
    await api("/api/invites", { method: "POST", body: JSON.stringify({ role }) });
    await loadInvites();
  } catch (e) {
    alert("Не удалось создать приглашение: " + e.message);
  }
};

$("#accessBtn").onclick = showAccessView;

$("#adminMenuToggleBtn").onclick = () => {
  const submenu = $("#adminSubmenu");
  const collapsed = submenu.classList.toggle("hidden");
  $("#adminMenuCaret").textContent = collapsed ? "▾" : "▴";
};

async function loadBlockingCases() {
  state.blockingCases = await api("/api/blocking-cases");
  populateBlockingAuthorFilter();
  populateBlockingWorkFilter();
  renderBlockingTable();
}

function renderBlockingTable() {
  const statusVal = $("#blockingStatusFilter").value;
  const authorVal = $("#blockingAuthorFilter").value;
  const workVal = $("#blockingWorkFilter").value;
  // Раздел "Постоянно блокируемые ссылки" убран 17.09.2026 — раньше
  // здесь дела, входящие хоть в одну "постоянно блокируемую" группу (см.
  // chronic_links.py), исключались из общей таблицы и показывались
  // только в том отдельном разделе. Теперь показываются как обычные
  // строки, вместе со всеми остальными.
  let rows = state.blockingCases;
  // фильтр по решению — совпадает хоть с одним из трёх этапов (общего
  // единого «Статуса» дела больше нет, см. storage.APPEAL_DECISIONS)
  if (statusVal) rows = rows.filter((c) => c.claim_decision === statusVal || caseAppeals(c).some((a) => a.decision === statusVal));
  if (authorVal) rows = rows.filter((c) => (c.author_name || "Без автора") === authorVal);
  if (workVal) rows = rows.filter((c) => (c.work_title || "Без произведения") === workVal);

  const body = $("#blockingBody");
  body.innerHTML = "";
  $("#blockingEmpty").classList.toggle("hidden", rows.length > 0);
  // убираем из выбора дела, которые сейчас не отображаются (например, статус сменился)
  const visibleIds = new Set(rows.map((c) => c.id));
  [...state.blockingSelection].forEach((id) => { if (!visibleIds.has(id)) state.blockingSelection.delete(id); });

  renderPetitionOverdueBanner(state.blockingCases);  // считаем по ВСЕМ делам, не только по отфильтрованным — иначе баннер может «пропасть» просто из-за выбранного фильтра

  // группируем по автору, чтобы ссылки не сливались в одну общую кучу
  const groups = new Map();
  rows.forEach((c) => {
    const key = c.author_name || "Без автора";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  });
  const sortedKeys = [...groups.keys()].sort((a, b) => a.localeCompare(b, "ru"));

  sortedKeys.forEach((authorKey) => {
    const groupRows = groups.get(authorKey);
    const headerTr = document.createElement("tr");
    headerTr.className = "blocking-author-header";
    headerTr.innerHTML = `<td colspan="22">${escapeHtml(authorKey)} <span class="blocking-author-count">— ${groupRows.length}</span></td>`;
    body.appendChild(headerTr);
    groupRows.forEach((c) => body.appendChild(renderBlockingRow(c)));
  });
  updateBlockingSelectionActionBar();
}

function renderPetitionOverdueBanner(allCases) {
  // Напоминание считается по чистой дате (>= 14 дней с подачи в МГС), не
  // дожидаясь результата фоновой автоматической проверки — специально на
  // случай, если фоновая проверка почему-то ещё не отработала (сервер был
  // выключен, наблюдатель не запустился и т.п.), чтобы сотрудник всё равно
  // видел, что пора обратить внимание, даже без needs_resend.
  const overdue = allCases.filter((c) => c.petition_filed_at && !c.link_status && daysSince(c.petition_filed_at) >= 14);
  const banner = $("#petitionOverdueBanner");
  if (overdue.length === 0) {
    banner.classList.add("hidden");
    return;
  }
  banner.classList.remove("hidden");
  banner.innerHTML = `⏰ ${overdue.length} ${overdue.length === 1 ? "дело" : "дел"}: прошло 14+ дней с подачи заявления в МГС, а автоматическая проверка ссылки ещё не отработала — стоит проверить вручную (кнопка «🔄 Проверить сейчас» у каждого дела ниже).`;
}

// Практическая транслитерация латиницы кириллицей — для билингвального
// формата в полях «Ответчик»/«Адрес ответчика» (см. подсказку у поля:
// «CloudFlare, Inc. (КлаудФлэр, Инк.)»). Это НЕ перевод по смыслу —
// официальное название/адрес ответчика для документов остаётся как есть,
// в скобки добавляется только фонетическая запись кириллицей, которую
// сотрудник может поправить вручную перед сохранением (например, если
// у организации уже есть устоявшееся русское написание).
const _TRANSLIT_MULTI = [
  ["shch", "щ"], ["kh", "х"], ["ts", "ц"], ["ch", "ч"], ["sh", "ш"],
  ["zh", "ж"], ["yu", "ю"], ["ya", "я"], ["ye", "е"], ["yo", "ё"],
  ["ph", "ф"], ["th", "т"], ["ck", "к"], ["qu", "кв"],
];
const _TRANSLIT_SINGLE = {
  a: "а", b: "б", c: "к", d: "д", e: "е", f: "ф", g: "г", h: "х", i: "и",
  j: "дж", k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", q: "к", r: "р",
  s: "с", t: "т", u: "у", v: "в", w: "в", x: "кс", y: "и", z: "з",
};

function transliterateToRu(text) {
  let lower = (text || "").toLowerCase();
  for (const [lat, ru] of _TRANSLIT_MULTI) {
    lower = lower.split(lat).join(ru);
  }
  let result = "";
  for (const ch of lower) {
    result += _TRANSLIT_SINGLE[ch] !== undefined ? _TRANSLIT_SINGLE[ch] : ch;
  }
  // Первая буква каждого «слова» — заглавная, похоже на оформление
  // названий компаний, а не сплошной строчный текст.
  return result.replace(/(^|[\s(),.])([а-яё])/gu, (m, sep, ch) => sep + ch.toUpperCase());
}

// Берёт только латинскую часть исходного текста (кириллица/цифры/пунктуация
// транслитерации не подлежат — нет смысла превращать то, что уже написано
// по-русски или является числом/индексом) и добавляет её транслитерацию
// в скобках в конец строки. Если скобка с транслитерацией уже похожа на
// существующую (совпадает первое слово), повторно не добавляет — иначе
// каждый клик плодил бы дубли при повторном нажатии на ту же ссылку.
function appendTransliteration(text) {
  const value = (text || "").trim();
  if (!value) return value;
  const latinWords = value.match(/[A-Za-z][A-Za-z'’.-]*/g);
  if (!latinWords || latinWords.length === 0) return value; // нечего транслитерировать
  const latinPart = latinWords.join(" ");
  const translit = transliterateToRu(latinPart);
  if (!translit) return value;
  const alreadyHasTranslit = new RegExp(`\\(\\s*${translit.split(" ")[0]}`, "i").test(value);
  if (alreadyHasTranslit) return value;
  return `${value} (${translit})`;
}

// Дело можно включить в заявление в суд, если оно ещё не заблокировано
// (либо заблокировано, но ссылка «ожила» снова — needs_resend), и либо
// заявление ещё не подавалось, либо предыдущая попытка провалилась —
// appealFailed — решение по 1-му/повторному обращению само по себе
// («отклонено»/«нет реакции») означает провал, для этого не нужно ждать
// ещё и автоматическую проверку ссылки через 14 дней (needs_resend) —
// это отдельный, более быстрый сигнал «нужно переподавать». Решение по
// досудебной претензии (claim_decision) сюда намеренно не входит — её
// провал означает просто «переходим к следующему этапу», а не «нужно
// переподавать то же самое обращение».
// Вынесено отдельной функцией (не только внутри renderBlockingRow) — та
// же проверка нужна и при подготовке заявления по общему выбору ссылок
// (единый чекбокс теперь доступен на любой строке, а не только на тех,
// что годятся для заявления).
function isPetitionEligible(c) {
  const isBlocked = !!c.is_blocked;
  const appealFailed = !!c.appeal_failed;
  return (!isBlocked || c.needs_resend) && (!c.petition_filed_at || c.needs_resend || appealFailed);
}

function renderBlockingRow(c) {
  const tr = document.createElement("tr");
  const who = c.work_title || "—";
  // Текущее состояние дела считает сервер (backend/appeals.py): решает
  // ПОСЛЕДНИЙ начатый этап (претензия → обращение №1 → №2 ...).
  const isBlocked = !!c.is_blocked;
  const hasAppealContent = caseAppeals(c).some(appealHasContent);
  // Заблокировано уже на претензии и ссылка не ожила — обращения не нужны.
  const resolvedAtClaim = c.claim_decision === "заблокировано" && !c.needs_resend && !hasAppealContent;
  tr.innerHTML = `
      <td><input type="checkbox" class="blocking-select-cb" ${state.blockingSelection.has(c.id) ? "checked" : ""} title="Выбрать эту ссылку — дальше можно подготовить заявление в суд или выгрузить список для формы РКН"></td>
      <td><div class="rkn-cell-date-row">
        <input type="date" data-field="discovered_at" value="${c.discovered_at || ""}" title="Дата обнаружения нарушения">
        <button type="button" class="row-btn" data-act="copy-url" title="Скопировать ссылку на нарушение в буфер обмена">🔗</button>
      </div></td>
      <td>${escapeHtml(who)}${c.source ? `<div class="r-desc r-desc-clamp" title="${escapeHtml(c.source)}">${escapeHtml(c.source)}</div>` : ""}</td>
      <td><div class="r-title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</div><a class="r-url" href="${escapeHtml(c.url)}" target="_blank" rel="noopener" title="${escapeHtml(c.url)}">${escapeHtml(shortenUrl(c.url))}</a>
        ${canAddSites() ? `<button type="button" class="row-btn row-btn-tiny" data-act="add-site-domain" title="Добавить домен этой ссылки в справочник «Поиск по сайтам»">➕ домен в справочник</button>` : ""}
        <label class="petition-filed-mark" title="Отметить, что заявление по этой ссылке фактически подано в суд">
          <input type="checkbox" data-field="petition_filed_at_toggle" ${c.petition_filed_at ? "checked" : ""}>
          ${c.petition_filed_at ? `Подано ${formatIsoDateRu(c.petition_filed_at)}` : "Подано"}
        </label>
        ${c.petition_filed_at ? `
        <div class="link-status-row">
          ${c.link_status
            ? `<span class="link-status-badge ${c.link_status === "доступна" ? "link-status-up" : "link-status-down"}">${c.link_status === "доступна" ? "🔴 ссылка доступна" : "✅ ссылка недоступна"} (${formatDocDate(c.link_checked_at)})</span>`
            : (daysSince(c.petition_filed_at) >= 14
                ? `<span class="link-status-badge link-status-up" title="Прошло ${daysSince(c.petition_filed_at)} дней с подачи заявления в МГС, а автоматическая проверка ещё не отработала — возможно, сервер был выключен в этот момент">⏰ 14 дней с подачи заявления в МГС прошло — проверьте вручную</span>`
                : `<span class="hint-text">Первая проверка — через 14 дней после подачи (прошло ${daysSince(c.petition_filed_at)})</span>`)}
          <button class="row-btn" data-act="check-link" title="Проверить доступность ссылки сейчас, не дожидаясь автоматической проверки">🔄 Проверить сейчас</button>
        </div>
        ${linkCheckDetailsHtml(c)}
        ${c.needs_resend && !isBlocked ? `<div class="link-status-row"><span class="link-status-badge link-status-up">⚠️ требуется повторное обращение — добавьте его в колонке «Обращения»</span></div>` : ""}
        ${confirmBlockedHtml(c)}
        <div class="link-status-row">
          <span class="hint-text">Повторять проверку:</span>
          <select data-field="link_check_interval" title="Как часто повторять проверку доступности после первого раза">
            <option value="hour" ${c.link_check_interval === "hour" ? "selected" : ""}>раз в час</option>
            <option value="day" ${!c.link_check_interval || c.link_check_interval === "day" ? "selected" : ""}>раз в день</option>
            <option value="week" ${c.link_check_interval === "week" ? "selected" : ""}>раз в неделю</option>
            <option value="month" ${c.link_check_interval === "month" ? "selected" : ""}>раз в месяц</option>
          </select>
        </div>` : isBlocked && c.block_date ? `
        <div class="link-status-row">
          ${c.link_status
            ? `<span class="link-status-badge ${c.link_status === "доступна" ? "link-status-up" : "link-status-down"}">${c.link_status === "доступна" ? "🔴 ссылка снова доступна" : "✅ по-прежнему недоступна"} (${formatDocDate(c.link_checked_at)})</span>`
            : `<span class="hint-text">Проверка на «ожила ли снова» — через 14 дней после блокировки</span>`}
          <button class="row-btn" data-act="check-link" title="Проверить доступность ссылки сейчас">🔄 Проверить сейчас</button>
        </div>
        ${linkCheckDetailsHtml(c)}
        ${confirmBlockedHtml(c)}
        <div class="link-status-row">
          <span class="hint-text">Повторять проверку:</span>
          <select data-field="link_check_interval" title="Как часто повторять проверку после первого раза">
            <option value="hour" ${c.link_check_interval === "hour" ? "selected" : ""}>раз в час</option>
            <option value="day" ${!c.link_check_interval || c.link_check_interval === "day" ? "selected" : ""}>раз в день</option>
            <option value="week" ${c.link_check_interval === "week" ? "selected" : ""}>раз в неделю</option>
            <option value="month" ${c.link_check_interval === "month" ? "selected" : ""}>раз в месяц</option>
          </select>
        </div>` : ""}
      </td>
      <td><div class="presence-cell">
        <label><input type="checkbox" data-field="presence_google" ${c.presence_google ? "checked" : ""}> Google</label>
        <label><input type="checkbox" data-field="presence_yandex" ${c.presence_yandex ? "checked" : ""}> Яндекс</label>
      </div></td>
      <td><div class="translit-cell">
        <input type="text" data-field="defendant" value="${escapeHtml(c.defendant || "")}" placeholder="хостинг-провайдер" list="defendantSuggestions">
        <button type="button" class="row-btn" data-act="translit-defendant" title="Добавить транслитерацию кириллицей в скобках — например, из «CloudFlare, Inc.» получится «CloudFlare, Inc. (КлаудФлэр, Инк.)». Это транслитерация (запись тем же звучанием), а не перевод — официальное название ответчика для документов остаётся неизменным.">🔤</button>
      </div></td>
      <td><div class="translit-cell">
        <input type="text" data-field="defendant_address" value="${escapeHtml(c.defendant_address || "")}" placeholder="адрес регистрации + полное наименование" title="Для заявления в суд — например: CloudFlare, Inc. (КлаудФлэр, Инк.) 101 Townsend St, San Francisco, CA 94107, USA. Подтягивается автоматически из RDAP, если провайдер публикует.">
        <button type="button" class="row-btn" data-act="translit-address" title="Добавить транслитерацию кириллицей в скобках (то же звучание, не перевод по смыслу) — официальный адрес/название останутся как есть, транслитерация только дополняет их в скобках.">🔤</button>
      </div></td>
      <td><div class="ip-cell">
        <input type="text" data-field="ip_address" value="${escapeHtml(c.ip_address || "")}" placeholder="0.0.0.0">
        <button type="button" class="row-btn" data-act="lookup-ip" title="Определить IP и хостинг заново по ссылке">🔄</button>
        <button type="button" class="row-btn" data-act="capture-whois" title="Автоматический скриншот 2ip.io (на русском) по этому IP — подтверждение для заявления">📋</button>
      </div></td>
      <td><button class="row-btn" data-act="shots">📷 ${c.screenshots_count || 0}</button></td>
      <td><div class="email-cell">
        <input type="email" data-field="defendant_email" value="${escapeHtml(c.defendant_email || "")}" placeholder="abuse@hosting.com">
        <button type="button" class="row-btn" data-act="complaint" title="Открыть черновик жалобы в Gmail — заодно проставит сегодняшнюю дату в «Дата претензии», если она ещё не заполнена">✉️</button>
      </div></td>
      <td><div class="rkn-cell-date-row">
        <input type="date" data-field="claim_date" value="${c.claim_date || ""}" title="Дата претензии. Ctrl+C — скопировать дату">
      </div></td>
      <td>
        <select data-field="claim_decision" class="blocking-status-select" data-status="${escapeHtml(c.claim_decision || "")}" title="Решение по досудебной претензии">
          ${APPEAL_DECISIONS.map((d) => `<option value="${d}" ${d === (c.claim_decision || "") ? "selected" : ""}>${d || "— не определено —"}</option>`).join("")}
        </select>
        ${c.claim_decision === "заблокировано" && !hasAppealContent ? `<div class="appeal-block-date"><span class="appeal-tag">блокировка</span><input type="date" data-field="block_date" value="${c.block_date || ""}" title="Дата блокировки"></div>` : ""}
      </td>
      <td>${(() => {
        const total = (c.presence_google && c.google_dmca_filed_at ? 1 : 0)
          + (c.other_complaints || []).length;
        return `<button class="row-btn" data-act="other-complaints">📢 Жалобы ${total}</button>`;
      })()}</td>
      <td>${renderAppealsCell(c, resolvedAtClaim)}</td>
      <td><textarea class="notes-textarea" data-field="notes" rows="1" placeholder="примечания">${escapeHtml(c.notes || "")}</textarea></td>
      <td><div class="cell-last-actions">
        <button class="row-btn danger" data-act="del">Удалить</button>
      </div></td>
    `;
  tr.querySelectorAll("input, select, textarea").forEach((el) => {
    if (!el.dataset.field) return;  // поля обращений сохраняются отдельно — см. wireAppealsCell
    el.addEventListener("change", () => {
      const value = el.type === "checkbox" ? el.checked : el.value;
      saveBlockingField(c.id, el.dataset.field, value, el, tr);
    });
  });
  // Поле «Примечания» раньше было однострочным <input> — длинный текст
  // физически нельзя было прочитать целиком, поле оставалось маленьким
  // (см. заметку разработки, 03.09). Теперь это <textarea>, по умолчанию
  // тоже компактная (1 строка, не растягивает таблицу), но по клику
  // разворачивается на всю высоту содержимого — и сворачивается обратно
  // при потере фокуса, если снова стала однострочной.
  const notesEl = tr.querySelector(".notes-textarea");
  if (notesEl) {
    const autoSize = () => { notesEl.style.height = "auto"; notesEl.style.height = notesEl.scrollHeight + "px"; };
    notesEl.addEventListener("focus", autoSize);
    notesEl.addEventListener("input", autoSize);
    notesEl.addEventListener("blur", () => { notesEl.style.height = ""; });
  }
  // Автоподстановка адреса из справочника KNOWN_DEFENDANTS — если введённое/
  // выбранное название ответчика совпадает с одним из известных, и поле
  // «Адрес ответчика» ещё пустое (не трогаем то, что уже заполнено вручную),
  // подставляем и сохраняем адрес сразу же, без отдельного клика.
  const defendantInput = tr.querySelector('[data-field="defendant"]');
  defendantInput.addEventListener("change", () => {
    const known = KNOWN_DEFENDANTS.find((d) => d.name === defendantInput.value.trim());
    if (!known) return;
    const addressInput = tr.querySelector('[data-field="defendant_address"]');
    if (addressInput.value.trim()) return; // уже заполнено вручную — не перезаписываем
    addressInput.value = known.address;
    saveBlockingField(c.id, "defendant_address", known.address, addressInput, tr);
  });
  tr.querySelector('[data-act="del"]').onclick = async () => {
    if (!confirm("Убрать эту ссылку из блокировки? Отменить нельзя.")) return;
    await api(`/api/blocking-cases/${c.id}`, { method: "DELETE" });
    state.blockingCases = state.blockingCases.filter((x) => x.id !== c.id);
    populateBlockingAuthorFilter();
    populateBlockingWorkFilter();
    refreshActiveBlockingLikeView();
  };
  tr.querySelector('[data-act="shots"]').onclick = () => openScreenshotsModal(c);
  tr.querySelector('[data-act="other-complaints"]').onclick = () => openOtherComplaintsModal(c);
  tr.querySelector('[data-act="copy-url"]').onclick = (e) => copyUrlOnly(c, e.currentTarget);
  tr.querySelector('[data-act="translit-defendant"]').onclick = () => {
    const input = tr.querySelector('[data-field="defendant"]');
    const next = appendTransliteration(input.value);
    if (next === input.value) return;
    input.value = next;
    saveBlockingField(c.id, "defendant", next, input, tr);
  };
  tr.querySelector('[data-act="translit-address"]').onclick = () => {
    const input = tr.querySelector('[data-field="defendant_address"]');
    const next = appendTransliteration(input.value);
    if (next === input.value) return;
    input.value = next;
    saveBlockingField(c.id, "defendant_address", next, input, tr);
  };
  tr.querySelector(".blocking-select-cb").onchange = (e) => {
    if (e.target.checked) state.blockingSelection.add(c.id);
    else state.blockingSelection.delete(c.id);
    updateBlockingSelectionActionBar();
  };

  const filedCheckbox = tr.querySelector('[data-field="petition_filed_at_toggle"]');
  filedCheckbox.onchange = async (e) => {
    const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
    const newValue = e.target.checked ? today : "";
    await saveBlockingField(c.id, "petition_filed_at", newValue, null);
    refreshActiveBlockingLikeView();
  };

  // Копирование дат: Ctrl+C в поле даты (см. обработчик keydown рядом с
  // renderAppealsCell) — серые поля-дубли убраны 23.09, занимали место.

  wireAppealsCell(c, tr);

  const confirmBtn = tr.querySelector('[data-act="confirm-blocked"]');
  if (confirmBtn) {
    confirmBtn.onclick = async () => {
      if (!confirm("Подтвердить, что ссылка на самом деле заблокирована (проверка ошиблась)? Дело уйдёт в архив, а такой же ответ сайта больше не будет считаться «ожившей» ссылкой.")) return;
      confirmBtn.disabled = true;
      try {
        const resp = await api(`/api/blocking-cases/${c.id}/confirm-blocked`, { method: "POST" });
        if (resp.auto_archived) {
          state.blockingCases = state.blockingCases.filter((x) => x.id !== c.id);
          state.blockingSelection.delete(c.id);
        } else {
          Object.assign(c, resp);
        }
        refreshActiveBlockingLikeView();
      } catch (err) {
        alert("Не удалось: " + err.message);
        confirmBtn.disabled = false;
      }
    };
  }

  const addSiteBtn = tr.querySelector('[data-act="add-site-domain"]');
  if (addSiteBtn) addSiteBtn.onclick = () => addDomainToSiteDirectory(c.url, addSiteBtn);

  const checkLinkBtn = tr.querySelector('[data-act="check-link"]');
  if (checkLinkBtn) {
    checkLinkBtn.onclick = async () => {
      checkLinkBtn.disabled = true;
      checkLinkBtn.textContent = "Проверяю…";
      try {
        const updated = await api(`/api/blocking-cases/${c.id}/check-link`, { method: "POST" });
        Object.assign(c, updated);
        refreshActiveBlockingLikeView();
      } catch (err) {
        alert("Не удалось проверить ссылку: " + err.message);
        checkLinkBtn.disabled = false;
        checkLinkBtn.textContent = "🔄 Проверить сейчас";
      }
    };
  }

  tr.querySelector('[data-act="lookup-ip"]').onclick = async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.textContent = "…";
    try {
      const updated = await api(`/api/blocking-cases/${c.id}/lookup-ip`, { method: "POST" });
      Object.assign(c, updated);
      refreshActiveBlockingLikeView();
    } catch (err) {
      alert("Не удалось определить IP: " + err.message);
      btn.disabled = false;
      btn.textContent = "🔄";
    }
  };

  tr.querySelector('[data-act="capture-whois"]').onclick = async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    const original = btn.textContent;
    try {
      btn.textContent = "…";
      const startRes = await fetch(`/api/blocking-cases/${c.id}/screenshots/capture-defendant-proof`, { method: "POST" });
      if (!startRes.ok) {
        const body = await startRes.json().catch(() => ({}));
        throw new Error(body.error || `Ошибка ${startRes.status}`);
      }
      const { job_id } = await startRes.json();
      let status, lastBody;
      let pollFailures = 0;
      do {
        await new Promise((r) => setTimeout(r, 1200));
        let pollRes;
        try {
          pollRes = await fetch(`/api/blocking-cases/${c.id}/screenshots/capture-defendant-proof/${job_id}`);
        } catch (netErr) {
          // сеть моргнула/сервер на секунду недоступен — не считаем это
          // сразу провалом задачи, пробуем ещё разок-другой
          if (++pollFailures > 5) throw new Error("Сервер не отвечает — попробуйте ещё раз позже");
          continue;
        }
        // сервер иногда может ответить не JSON'ом, а HTML-страницей ошибки
        // (502/504 от nginx, если backend был на секунду перегружен) —
        // раньше это падало с непонятным «Unexpected token '<'»
        const body = await pollRes.json().catch(() => null);
        if (body === null) {
          if (++pollFailures > 5) throw new Error(`Сервер вернул неожиданный ответ (${pollRes.status}) — попробуйте ещё раз позже`);
          continue;
        }
        pollFailures = 0;
        lastBody = body;
        status = body.status;
        if (status === "error") throw new Error(body.error || "Не удалось сделать снимок WHOIS");
      } while (status !== "done");
      btn.textContent = "✓";
      setTimeout(() => { btn.textContent = original; }, 2000);
      // Сверка «Ответчика» с тем, что реально показывает RDAP по этому
      // IP — если поле «Ответчик» разошлось с фактическим владельцем IP
      // (например, ссылка переехала на другой хостинг, а поле осталось
      // от старого), предупреждаем сразу же. Снимок при этом всё равно
      // сохранён — предупреждение не блокирует, только сигнализирует;
      // расхождение также записано в описание самого снимка на будущее.
      const check = lastBody.defendant_check;
      if (check && check.checked && !check.matches) {
        alert(
          `⚠️ Расхождение: по данным RDAP этот IP (${c.ip_address || ""}) принадлежит «${check.rdap_org}», ` +
          `а в поле «Ответчик» указано «${c.defendant || ""}».\n\n` +
          `Возможно, ссылка переехала на другой хостинг после того, как поле было заполнено. ` +
          `Снимок сохранён как есть — проверьте и поправьте поле «Ответчик», если нужно.`
        );
      }
    } catch (err) {
      alert("Не удалось сделать снимок подтверждения хостинга: " + err.message);
      btn.textContent = original;
    } finally {
      btn.disabled = false;
    }
  };

  tr.querySelector('[data-act="complaint"]').onclick = async () => {
    try {
      const draft = await api(`/api/blocking-cases/${c.id}/complaint-email`);
      if (!draft.to) {
        alert("У этого дела не заполнен email ответчика — сначала укажите его в колонке «Email ответчика».");
        return;
      }
      openGmailCompose(draft.to, draft.subject, draft.body);
      // фиксируем дату претензии автоматически — но только если она ещё не
      // проставлена вручную (мы не можем знать, реально ли письмо было
      // отправлено, раз оно уходит через почтовый клиент, а не наш сервер —
      // но открытие черновика для отправки лучший наблюдаемый нами момент,
      // чтобы отметить дату претензии сами, не заставляя вписывать её руками)
      if (!c.claim_date) {
        const today = new Date().toISOString().slice(0, 10);
        const updated = await api(`/api/blocking-cases/${c.id}`, {
          method: "PUT", body: JSON.stringify({ claim_date: today }),
        });
        Object.assign(c, updated);
        refreshActiveBlockingLikeView();
      }
    } catch (err) {
      alert("Не удалось подготовить письмо: " + err.message);
    }
  };

  return tr;
}

// Открывает окно создания письма в Gmail (в браузере) с уже заполненными
// полями. Письмо не отправляется автоматически — уходит с того аккаунта,
// в который человек залогинен в Gmail, отправка — его собственным кликом.
// Файл (скриншот) браузер прикрепить не может по соображениям безопасности —
// это ограничение самого Gmail/браузера, а не приложения.
function openGmailCompose(to, subject, body) {
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    to,
    su: subject,
    body,
  });
  window.open(`https://mail.google.com/mail/?${params.toString()}`, "_blank", "noopener");
}

function populateBlockingAuthorFilter() {
  const sel = $("#blockingAuthorFilter");
  const prev = sel.value;
  const names = [...new Set(state.blockingCases.map((c) => c.author_name || "Без автора"))].sort((a, b) => a.localeCompare(b, "ru"));
  sel.innerHTML = `<option value="">Все</option>` + names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
  if (names.includes(prev)) sel.value = prev;
}

function populateBlockingWorkFilter() {
  const sel = $("#blockingWorkFilter");
  const prev = sel.value;
  // Каскадный список: если выбран конкретный автор, показываем только его
  // произведения, а не всех авторов сразу — раньше список не учитывал
  // выбор автора вообще, из-за чего у Гордынца в списке "Произведение"
  // показывались и произведения других авторов тоже.
  const authorVal = $("#blockingAuthorFilter").value;
  const relevantCases = authorVal
    ? state.blockingCases.filter((c) => (c.author_name || "Без автора") === authorVal)
    : state.blockingCases;
  const titles = [...new Set(relevantCases.map((c) => c.work_title || "Без произведения"))].sort((a, b) => a.localeCompare(b, "ru"));
  sel.innerHTML = `<option value="">Все</option>` + titles.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
  // Если ранее выбранного произведения нет среди произведений нового
  // автора — сбрасываем на "Все", а не оставляем невидимое несуществующее
  // значение выбранным (иначе фильтр по факту продолжит действовать на
  // невидимое пользователю значение).
  sel.value = titles.includes(prev) ? prev : "";
}

async function saveBlockingField(caseId, field, value, el, rowEl) {
  try {
    const resp = await api(`/api/blocking-cases/${caseId}`, { method: "PUT", body: JSON.stringify({ [field]: value }) });

    // Дело стало по-настоящему «закрытым» (заблокировано + проверка
    // ссылки подтверждает, что оно недоступно) — сервер сам перенёс его
    // в архив отчётов (см. app.py, _maybe_auto_archive_blocked_case) и
    // сообщил об этом флагом. Убираем строку из активных списков сразу,
    // не дожидаясь полной перезагрузки — иначе дело выглядело бы так,
    // будто оно всё ещё в «Блокировке», хотя на сервере его там уже нет.
    if (resp && resp.auto_archived) {
      state.blockingCases = state.blockingCases.filter((x) => x.id !== caseId);
      state.blockingSelection.delete(caseId);
      renderBlockingTable();
      return;
    }

    const c = state.blockingCases.find((x) => x.id === caseId);
    if (c) {
      c[field] = value;
      if (resp && typeof resp === "object") Object.assign(c, resp);  // сервер вернул дело с пересчитанным состоянием
    }
    if ((field === "claim_decision" || field === "first_appeal_decision" || field === "repeat_appeal_decision") && el) {
      el.dataset.status = value;
    }
    // Поля дат с кнопкой "скопировать" — обновляем точечно (не всю строку,
    // см. комментарий ниже про потерю фокуса), чтобы кнопка/копируемый
    // текст появлялись сразу после ввода даты, а не только после
    // следующей перезагрузки/переключения раздела.
    if (field === "claim_decision" || field === "presence_google") {
      // От первых трёх зависит видимость бейджа «⚠️ повторить» и скрытие
      // ненужных столбцов; presence_google — доступность фиксированного
      // раздела «Google DMCA» в окне «Жалобы» (имеет смысл, только если
      // ссылка реально есть в выдаче Google). court_ruling_date раньше
      // тоже был в этом списке (для видимости чекбокса «Для РКН»), но с
      // объединением выбора в один общий чекбокс на строку эта причина
      // отпала — а перерисовывать строку при вводе даты было вредно:
      // <input type="date"> у некоторых браузеров может прислать событие
      // "change" ещё до того, как год дописан полностью (например, после
      // 2 введённых цифр), и полная перерисовка строки в этот момент
      // обрывала фокус и «сбрасывала» недописанную дату. Все эти
      // флаги зависят только от данных этого дела, не от других строк —
      // перерисовываем только эту строку, не всю таблицу (при сотнях+
      // дел полная перерисовка на каждый клик заметно подвисала,
      // проверено: свыше секунды при 1000 дел).
      if (c && rowEl && rowEl.parentNode) {
        const newRow = renderBlockingRow(c);
        rowEl.replaceWith(newRow);
        updateBlockingSelectionActionBar();  // чекбокс мог исчезнуть/появиться у этой строки — панель "Выбрано" должна это отразить
      }
    }
  } catch (e) {
    alert("Не удалось сохранить: " + e.message);
  }
}

// ---------- Источники поиска и справочник сайтов (обновление 23.09) ----------
const SOURCE_STATUS_LABELS = { ok: "выполнено", error: "ошибка", not_configured: "не настроен" };
const SITE_MODE_SHORT = { template: "только шаблон", xenforo: "XenForo", yandex: "через Яндекс", manual: "ручная проверка", off: "отключён" };
const SITE_STATUS_LABELS = {
  ok: "работает", empty: "работает, пусто", no_template: "шаблон поиска не задан",
  blocked: "защита от ботов", unavailable: "недоступен", error: "ошибка поиска", skipped: "не ищется",
};
const SITE_PROBLEM_STATUSES = ["no_template", "blocked", "unavailable", "error"];

function siteModeOf(s) {
  if (s.mode) return s.mode;
  return s.type === "xenforo" ? "xenforo" : "auto";
}

function siteNeedsSetup(s) {
  const mode = siteModeOf(s);
  if (["manual", "off"].includes(mode)) return false;
  if (SITE_PROBLEM_STATUSES.includes(s.last_status)) return true;
  // ещё не проверялся: без {query} в режиме «автоматически» почти наверняка ищет вхолостую
  return !s.last_status && mode === "auto" && !(s.url_template || "").includes("{query}");
}

function applySourceAvailability() {
  // Источник без ключа не выдаёт выдуманных результатов — его галочка
  // неактивна, с пояснением. Уже отмеченные галочки не снимаются молча:
  // в отчёте после поиска будет видно «не настроен».
  const s = state.settings || {};
  const rules = [
    ["#srcGoogle", s.google_demo_blocked, "Google не настроен: без ключа API источник отключён (раньше выдавал демо-ссылки)"],
    ["#srcVk", s.vk_configured === false, "VK не настроен: нужен ключ VK_SERVICE_TOKEN на сервере"],
    ["#srcVkVideo", s.vk_video_configured === false, "Поиск видео VK не настроен: нужен ключ VK_USER_TOKEN на сервере"],
    ["#srcTorrents", s.torrents_configured === false, "Торрент-агрегатор не настроен: нужен TORZNAB_URL на сервере"],
  ];
  rules.forEach(([sel, off, why]) => {
    const el = $(sel);
    if (!el) return;
    el.disabled = !!off && !el.checked;
    el.parentElement.title = off ? why : "";
    el.parentElement.classList.toggle("source-off", !!off);
  });
}

function renderSourceReport(report) {
  const box = $("#sourceReport");
  if (!box) return;
  const entries = Object.entries(report || {});
  if (!entries.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  box.classList.remove("hidden");
  box.innerHTML = `<div class="source-report-title">Итоги по источникам</div>` + entries.map(([label, r]) => `
    <div class="source-report-row source-${escapeHtml(r.status)}">
      <b>${escapeHtml(label)}</b>: ${escapeHtml(SOURCE_STATUS_LABELS[r.status] || r.status)}${r.status === "ok" ? `, найдено ${r.found}` : ""}
      ${(r.errors || []).length ? `<span class="hint-text"> — ${escapeHtml(r.errors.join("; "))}</span>` : ""}
    </div>`).join("");
}

function renderSiteReport(data) {
  const box = $("#siteSearchReport");
  if (!box) return;
  const rows = (data && data.site_report) || [];
  if (!rows.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  const counts = {};
  rows.forEach((r) => { const k = r.status || "not_reached"; counts[k] = (counts[k] || 0) + 1; });
  const searched = (counts.ok || 0) + (counts.empty || 0);
  const problems = rows.filter((r) => SITE_PROBLEM_STATUSES.includes(r.status));
  const summary = Object.entries(counts)
    .map(([k, n]) => `${SITE_STATUS_LABELS[k] || (k === "not_reached" ? "не дошла очередь" : k)}: ${n}`).join(" · ");
  box.classList.remove("hidden");
  box.innerHTML = `<div class="source-report-title">Реально проверено сайтов: ${searched} из ${rows.length}</div>
    <div class="hint-text">${escapeHtml(summary)}</div>
    ${problems.length ? `<details><summary>Сайты, по которым поиск не выполнен (${problems.length}) — их стоит настроить</summary>
      ${problems.map((r) => `<div class="source-report-row source-error"><b>${escapeHtml(r.name)}</b>: ${escapeHtml(SITE_STATUS_LABELS[r.status] || r.status)}${r.detail ? `<span class="hint-text"> — ${escapeHtml(r.detail)}</span>` : ""}</div>`).join("")}
    </details>` : ""}`;
}

async function testSiteSetup(site, btn) {
  const firstQuery = ($("#siteSearchQuery").value.split("\n").map((x) => x.trim()).find(Boolean)) || "";
  const query = prompt(`Пробный поиск по сайту «${site.name}». Введите фамилию или название курса, который на этом сайте точно есть:`, firstQuery);
  if (query === null || !query.trim()) return;
  btn.disabled = true;
  btn.textContent = "Проверяю…";
  try {
    const r = await api(`/api/sites/${site.id}/test`, { method: "POST", body: JSON.stringify({ query: query.trim() }) });
    const sample = (r.sample || []).map((x) => `• ${x.title || x.url}`).join("\n");
    alert(`${site.name}: ${r.status_label}. Найдено ссылок: ${r.found}.` +
      (r.detail ? `\n\nПодробности: ${r.detail}` : "") + (sample ? `\n\nПервые результаты:\n${sample}` : "") +
      (r.status === "no_template" ? "\n\nЗадайте шаблон поиска с {query} (кнопка «Изменить»)." : ""));
  } catch (e) {
    alert("Проверка не удалась: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Проверить";
    loadSiteDirectory();
  }
}

async function checkCertStatus() {
  // Сертификат Let's Encrypt на IP живёт ~6 дней и продлевается сам;
  // предупреждаем администратора заранее, если продление сломалось.
  try {
    const c = await api("/api/admin/cert-status");
    const el = $("#certWarning");
    if (!el || !c.monitored) return;
    if (c.error || c.days_left < 2) {
      el.classList.remove("hidden");
      el.textContent = c.error
        ? `⚠️ Не удалось проверить сертификат HTTPS (${c.error}). Проверьте на сервере: bash c.sh status`
        : `⚠️ Сертификат HTTPS истекает через ${c.days_left < 1 ? "менее суток" : Math.floor(c.days_left) + " дн."} — автопродление, похоже, не сработало. Проверьте на сервере: bash c.sh status`;
    }
  } catch (e) { /* не критично */ }
}

$("#siteDirFilter").onchange = () => renderSiteDirectory();


// ---------- Обращения в МГС и РКН (обновление 23.09) ----------
// Вместо отдельных колонок «№ определения», «Обращение в РКН», «Решение
// (1-е)», «Повторное обращение», «Решение (повторное)», «Дата блокировки»,
// «Повторное решение» — одна колонка с повторяющимися блоками:
//   №1  МГС [дата определения][№]  РКН [дата][№]  [статус]
//   №2  ... (появляется кнопкой, когда №1 отклонено/без реакции или ссылка ожила)
// Логику «какой этап сейчас решает» считает сервер (backend/appeals.py).
const APPEAL_KEYS = ["mgs_date", "mgs_number", "rkn_date", "rkn_number", "decision"];

function emptyAppeal() {
  return { mgs_date: "", mgs_number: "", rkn_date: "", rkn_number: "", decision: "" };
}

function caseAppeals(c) {
  return Array.isArray(c.appeals) ? c.appeals : [];
}

function appealHasContent(a) {
  return !!a && APPEAL_KEYS.some((k) => a[k]);
}

function canAddSites() {
  // Добавлять сайты в справочник может любой редактор; менять и удалять —
  // только admin или по временному разрешению (state.canEditSites).
  return state.canEditSites || state.role === "editor" || state.role === "admin";
}

function renderAppealsCell(c, resolvedAtClaim) {
  if (resolvedAtClaim) {
    return `<span class="stage-not-needed" title="Заблокировано уже на этапе претензии — обращения в МГС и РКН не понадобились">—</span>`;
  }
  let list = caseAppeals(c);
  if (!list.length) list = [emptyAppeal()];  // пустой блок №1 — сразу есть куда вводить
  const last = list[list.length - 1];
  const lastFailed = last.decision === "отклонено" || last.decision === "нет реакции";
  const canAddNext = appealHasContent(last) && (lastFailed || c.needs_resend);
  // Дата блокировки показывается у того обращения, которое сейчас даёт
  // «заблокировано» (последнее заполненное).
  let blockedIdx = -1;
  if (c.is_blocked) {
    for (let i = list.length - 1; i >= 0; i--) {
      if (appealHasContent(list[i])) { if (list[i].decision === "заблокировано") blockedIdx = i; break; }
    }
  }
  const blocks = list.map((a, i) => `
    <div class="appeal-block" data-idx="${i}">
      <span class="appeal-num" title="Обращение №${i + 1}">№${i + 1}</span>
      <span class="appeal-group">
        <span class="appeal-tag">МГС</span>
        <input type="date" data-appeal="mgs_date" value="${escapeHtml(a.mgs_date || "")}" title="Дата определения Мосгорсуда. Ctrl+C — скопировать дату">
        <input type="text" data-appeal="mgs_number" value="${escapeHtml(a.mgs_number || "")}" placeholder="№ определения" title="Номер определения Мосгорсуда, например 2И-6684">
      </span>
      <span class="appeal-group">
        <span class="appeal-tag">РКН</span>
        <input type="date" data-appeal="rkn_date" value="${escapeHtml(a.rkn_date || "")}" title="Дата обращения в Роскомнадзор. Ctrl+C — скопировать дату">
        <input type="text" data-appeal="rkn_number" value="${escapeHtml(a.rkn_number || "")}" placeholder="№ обращения" title="Номер обращения в Роскомнадзор">
      </span>
      <select data-appeal="decision" class="blocking-status-select" data-status="${escapeHtml(a.decision || "")}" title="Статус обращения №${i + 1}">
        ${APPEAL_DECISIONS.map((d) => `<option value="${d}" ${d === (a.decision || "") ? "selected" : ""}>${d || "— не определено —"}</option>`).join("")}
      </select>
      ${i === blockedIdx ? `<span class="appeal-group"><span class="appeal-tag">блокировка</span><input type="date" data-field="block_date" value="${c.block_date || ""}" title="Дата блокировки"></span>` : ""}
      ${i > 0 && i === list.length - 1 && !appealHasContent(a) ? `<button type="button" class="row-btn" data-act="appeal-remove" title="Убрать пустое обращение">✕</button>` : ""}
    </div>`).join("");
  return `<div class="appeals-cell">
    ${blocks}
    ${canAddNext ? `<button type="button" class="row-btn appeal-add-btn" data-act="appeal-add" title="Добавить следующее обращение в МГС и РКН">+ Повторное обращение №${list.length + 1}</button>` : ""}
  </div>`;
}

function collectAppealsFromRow(tr) {
  return [...tr.querySelectorAll(".appeal-block")].map((block) => {
    const a = emptyAppeal();
    block.querySelectorAll("[data-appeal]").forEach((el) => { a[el.dataset.appeal] = el.value.trim(); });
    return a;
  });
}

async function saveAppeals(c, list, tr, rerender) {
  try {
    const resp = await api(`/api/blocking-cases/${c.id}`, { method: "PUT", body: JSON.stringify({ appeals: list }) });
    if (resp && resp.auto_archived) {
      state.blockingCases = state.blockingCases.filter((x) => x.id !== c.id);
      state.blockingSelection.delete(c.id);
      renderBlockingTable();
      return;
    }
    Object.assign(c, resp);
    // Даты и номера сохраняем БЕЗ перерисовки строки: <input type="date">
    // присылает change ещё до того, как год дописан, и перерисовка
    // обрывала бы ввод. Перерисовываем только при смене статуса и при
    // добавлении/удалении обращения — от них зависят кнопки и подсветка.
    if (rerender && tr && tr.parentNode) {
      tr.replaceWith(renderBlockingRow(c));
      updateBlockingSelectionActionBar();
    }
  } catch (e) {
    alert("Не удалось сохранить обращение: " + e.message);
  }
}

function wireAppealsCell(c, tr) {
  tr.querySelectorAll("[data-appeal]").forEach((el) => {
    el.addEventListener("change", () => {
      if (el.dataset.appeal === "decision") el.dataset.status = el.value;
      saveAppeals(c, collectAppealsFromRow(tr), tr, el.dataset.appeal === "decision");
    });
  });
  const addBtn = tr.querySelector('[data-act="appeal-add"]');
  if (addBtn) addBtn.onclick = () => saveAppeals(c, [...collectAppealsFromRow(tr), emptyAppeal()], tr, true);
  const removeBtn = tr.querySelector('[data-act="appeal-remove"]');
  if (removeBtn) removeBtn.onclick = () => {
    const current = collectAppealsFromRow(tr);
    // Кнопка ✕ рисуется у пустого блока, но пока строка не перерисована,
    // в него уже могли что-то ввести — не удаляем введённое молча.
    if (appealHasContent(current[current.length - 1]) && !confirm("В этом обращении уже есть данные. Удалить его?")) return;
    saveAppeals(c, current.slice(0, -1), tr, true);
  };
}

function appealsSummaryHtml(c) {
  const list = caseAppeals(c).filter(appealHasContent);
  if (!list.length) return "—";
  return list.map((a, i) => {
    const mgs = [a.mgs_date ? formatIsoDateRu(a.mgs_date) : "", a.mgs_number].filter(Boolean).join(" ");
    const rkn = [a.rkn_date ? formatIsoDateRu(a.rkn_date) : "", a.rkn_number ? "№ " + a.rkn_number : ""].filter(Boolean).join(" ");
    const parts = [mgs ? "МГС " + mgs : "", rkn ? "РКН " + rkn : "", a.decision || "не определено"].filter(Boolean);
    return `<div class="appeal-summary-line">№${i + 1}: ${escapeHtml(parts.join(" · "))}</div>`;
  }).join("");
}

// Почему проверка решила, что ссылка «снова доступна» — чтобы сразу было
// видно, реальный это сайт или страница-заглушка.
function linkCheckDetailsHtml(c) {
  const d = c.link_check_details;
  if (!d || c.link_status !== "доступна") return "";
  let host = "";
  try { host = d.final_url ? new URL(d.final_url).host : ""; } catch (e) { host = d.final_url || ""; }
  const parts = [d.http_code ? `код ${d.http_code}` : "", host, d.title ? `«${d.title}»` : ""].filter(Boolean);
  const proxyNote = d.via_proxy ? "" : " Проверка шла без российского прокси — заблокированные РКН сайты с зарубежного сервера открываются.";
  return `<div class="link-check-details" title="Ответ сайта при последней проверке.${proxyNote}">Ответ сайта: ${escapeHtml(parts.join(" · ") || "—")}${d.via_proxy ? "" : " <span class=\"link-check-warn\">(без RU-прокси)</span>"}</div>`;
}

function confirmBlockedHtml(c) {
  if (!(c.is_blocked && c.needs_resend)) return "";
  return `<div class="link-status-row"><button type="button" class="row-btn row-btn-confirm" data-act="confirm-blocked" title="Проверка ошиблась: ссылка на самом деле заблокирована. Дело уйдёт в архив, такой же ответ сайта больше не будет поднимать тревогу.">✅ Ложная тревога — ссылка заблокирована</button></div>`;
}

async function addDomainToSiteDirectory(url, btn) {
  let host = "";
  try { host = new URL(url).hostname; } catch (e) { alert("Не удалось разобрать адрес ссылки"); return; }
  const name = prompt("Название сайта для справочника «Поиск по сайтам»:", host);
  if (name === null) return;
  btn.disabled = true;
  try {
    await api("/api/sites", { method: "POST", body: JSON.stringify({ name: name.trim() || host, url_template: `https://${host}`, type: "auto" }) });
    btn.textContent = "✓ в справочнике";
    try { state.sites = await api("/api/sites"); } catch (e) { /* не критично */ }
  } catch (e) {
    alert(e.message);
    btn.disabled = false;
  }
}

// Копирование даты: серые поля-дубли убраны, вместо них Ctrl+C (⌘+C) в
// любом поле даты копирует её в привычном виде ДД.ММ.ГГГГ.
document.addEventListener("keydown", (e) => {
  const el = e.target;
  if (!(el instanceof HTMLInputElement) || el.type !== "date" || !el.value) return;
  if (!(e.ctrlKey || e.metaKey) || (e.key !== "c" && e.key !== "с" && e.code !== "KeyC")) return;
  e.preventDefault();
  const text = formatIsoDateRu(el.value);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => flashCopied(el), () => {});
  }
});

function flashCopied(el) {
  el.classList.add("date-copied");
  setTimeout(() => el.classList.remove("date-copied"), 700);
}

$("#blockingStatusFilter").innerHTML =
  `<option value="">Все</option>` + APPEAL_DECISIONS.filter(Boolean).map((s) => `<option value="${s}">${s}</option>`).join("");
$("#blockingStatusFilter").onchange = renderBlockingTable;
$("#blockingAuthorFilter").onchange = () => {
  populateBlockingWorkFilter();  // список произведений сужается под выбранного автора
  renderBlockingTable();
};
$("#blockingWorkFilter").onchange = renderBlockingTable;

// Справочник известных ответчиков (см. KNOWN_DEFENDANTS выше) — заполняет
// подсказки поля «Ответчик» один раз при загрузке страницы.
$("#defendantSuggestions").innerHTML = KNOWN_DEFENDANTS.map((d) => `<option value="${escapeHtml(d.name)}">`).join("");

$("#exportBlockingCsvBtn").onclick = () => {
  window.location.href = "/api/blocking-cases/export.csv";
};

// по умолчанию — текущий месяц
(() => {
  const now = new Date();
  const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  $("#reportMonth").value = ym;
})();

$("#downloadMonthlyReportBtn").onclick = () => {
  const month = $("#reportMonth").value; // YYYY-MM
  if (!month) { alert("Выберите месяц"); return; }
  window.location.href = `/api/blocking-cases/monthly-report?month=${month}`;
};

$("#finalizeMonthlyReportBtn").onclick = async () => {
  const month = $("#reportMonth").value;
  if (!month) { alert("Выберите месяц"); return; }
  if (!confirm(
    `Скачать отчёт за ${month} и убрать все вошедшие в него заблокированные дела из активной таблицы?\n\n` +
    `Дела не удаляются безвозвратно — переносятся в архив отчётов по каждому автору, доступный из карточки автора.`
  )) return;

  const btn = $("#finalizeMonthlyReportBtn");
  btn.disabled = true;
  try {
    const res = await fetch("/api/blocking-cases/monthly-report/finalize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ month }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${res.status}`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `otchet_blokirovka_${month}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
    await loadBlockingCases();
  } catch (err) {
    alert("Не удалось завершить месяц: " + err.message);
  } finally {
    btn.disabled = false;
  }
};

$("#blockingBtn").onclick = showBlockingView;

// ---------- изменяемая ширина столбцов «Произведение»/«Ссылка» ----------
// По просьбе от 17.09.2026 — раньше ширина этих двух закреплённых
// (position: sticky) столбцов была жёстко зашита в CSS (150px/300px), из-за
// чего длинные названия/ссылки обрезались без возможности их расширить.
// Теперь ширина хранится в CSS-переменных на самом элементе таблицы (см.
// --col-title-width/--col-link-width в styles.css) и меняется
// перетаскиванием ручки в заголовке; выбор запоминается в localStorage
// этого браузера (не общий — у каждого сотрудника может быть своё удобное
// значение, как ширина колонок в Excel).
(function initColumnResize() {
  const table = document.querySelector(".blocking-table");
  if (!table) return;
  const STORAGE_KEY = "blockingColumnWidths";
  const LIMITS = {
    discovered: { min: 90, max: 350, default: 175 },
    title: { min: 90, max: 520, default: 150 },
    link: { min: 140, max: 780, default: 300 },
  };

  function setWidth(col, px) {
    table.style.setProperty(`--col-${col}-width`, px + "px");
  }
  function getWidth(col) {
    const raw = getComputedStyle(table).getPropertyValue(`--col-${col}-width`);
    return parseFloat(raw) || LIMITS[col].default;
  }

  // Восстанавливаем сохранённое в этом браузере — если ключа ещё нет или
  // он повреждён (например, ручное вмешательство в localStorage), просто
  // остаёмся на значениях по умолчанию из styles.css, ничего не падает.
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    Object.keys(LIMITS).forEach((col) => {
      const v = saved[col];
      if (typeof v === "number" && v >= LIMITS[col].min && v <= LIMITS[col].max) setWidth(col, v);
    });
  } catch (e) { /* битые данные в localStorage — не критично, просто игнорируем */ }

  table.querySelectorAll(".col-resize-handle").forEach((handle) => {
    const col = handle.dataset.col; // "title" | "link"
    if (!LIMITS[col]) return;
    handle.addEventListener("mousedown", (e) => {
      e.preventDefault();  // не даём выделиться тексту заголовка во время перетаскивания
      const { min, max } = LIMITS[col];
      const startX = e.clientX;
      const startWidth = getWidth(col);
      handle.classList.add("col-resizing");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      function onMove(ev) {
        const next = Math.min(max, Math.max(min, startWidth + (ev.clientX - startX)));
        setWidth(col, next);
      }
      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        handle.classList.remove("col-resizing");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        try {
          const current = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
          current[col] = getWidth(col);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
        } catch (e) { /* localStorage недоступен (приватный режим и т.п.) — просто не запоминаем между сессиями */ }
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });
})();

async function loadSiteDirectory() {
  // Раньше при сбое загрузки раздел молча оставался пустым — выглядело как
  // пропажа всего справочника. Теперь — явная ошибка и кнопка «Повторить».
  try {
    state.sites = await api("/api/sites");
  } catch (e) {
    $("#siteDirectory").innerHTML = `<div class="demo-banner">Не удалось загрузить справочник сайтов (${escapeHtml(e.message)}). Данные на сервере не затронуты.
      <button class="row-btn" id="siteDirRetryBtn">Повторить</button></div>`;
    $("#siteDirRetryBtn").onclick = () => loadSiteDirectory();
    return;
  }
  renderSiteDirectory();
}

function renderSiteDirectory() {
  const box = $("#siteDirectory");
  $("#newSiteBtn").classList.toggle("hidden", !canAddSites());
  if (!state.sites.length) {
    box.innerHTML = `<p class="hint-text">Справочник пуст — добавьте первый сайт кнопкой ниже.</p>`;
    $("#siteDirStats").textContent = "";
    return;
  }
  const filter = $("#siteDirFilter").value;
  const setupCount = state.sites.filter(siteNeedsSetup).length;
  const skippedCount = state.sites.filter((s) => ["manual", "off"].includes(siteModeOf(s))).length;
  $("#siteDirStats").textContent = `Всего ${state.sites.length}; требуют настройки: ${setupCount}; ручных и отключённых: ${skippedCount}`;
  const visible = state.sites.filter((s) => {
    if (filter === "setup") return siteNeedsSetup(s);
    if (filter === "high") return s.priority === "high";
    if (filter === "skipped") return ["manual", "off"].includes(siteModeOf(s));
    return true;
  });
  box.innerHTML = visible.length ? "" : `<p class="hint-text">Под этот фильтр сайтов нет.</p>`;
  visible.forEach((s) => {
    const row = document.createElement("div");
    row.className = "site-row";
    const mode = siteModeOf(s);
    const badges = [];
    if (mode !== "auto") badges.push(`<span class="site-badge">${escapeHtml(SITE_MODE_SHORT[mode] || mode)}</span>`);
    if (s.priority === "high") badges.push(`<span class="site-badge site-badge-high">высокий приоритет</span>`);
    if (s.priority === "low") badges.push(`<span class="site-badge">низкий приоритет</span>`);
    if (s.last_status) {
      const when = s.last_checked_at ? new Date(s.last_checked_at * 1000).toLocaleDateString("ru-RU") : "";
      badges.push(`<span class="site-badge site-status-${escapeHtml(s.last_status)}" title="${escapeHtml(s.last_status_detail || "")}">${escapeHtml(SITE_STATUS_LABELS[s.last_status] || s.last_status)}${when ? " · " + when : ""}</span>`);
    } else if (siteNeedsSetup(s)) {
      badges.push(`<span class="site-badge site-status-no_template">шаблон поиска не задан</span>`);
    }
    if (s.found_total) badges.push(`<span class="site-badge" title="Сколько ссылок нашлось на этом сайте за всё время">найдено всего: ${s.found_total}</span>`);
    const mirrors = (s.mirrors || []).length ? `<div class="site-row-url">зеркала: ${escapeHtml(s.mirrors.join(", "))}</div>` : "";
    const notes = s.notes ? `<div class="site-row-notes">${escapeHtml(s.notes)}</div>` : "";
    row.innerHTML = `
      <div>
        <div class="site-row-name">${escapeHtml(s.name)} ${badges.join(" ")}</div>
        <div class="site-row-url">${escapeHtml(s.url_template)}</div>
        ${mirrors}${notes}
      </div>
      <div class="site-row-actions">
        ${canAddSites() ? '<button class="row-btn" data-act="test" title="Один пробный поиск по этому сайту — сразу видно, работает ли настройка">Проверить</button>' : ""}
        ${state.canEditSites ? '<button class="row-btn" data-act="edit">Изменить</button>' : ""}
        ${state.canEditSites ? '<button class="row-btn danger" data-act="del">Удалить</button>' : ""}
      </div>
    `;
    const testBtn = row.querySelector('[data-act="test"]');
    if (testBtn) testBtn.onclick = () => testSiteSetup(s, testBtn);
    if (state.canEditSites) {
      row.querySelector('[data-act="edit"]').onclick = () => openSiteModal(s);
      row.querySelector('[data-act="del"]').onclick = async () => {
        if (!confirm(`Удалить сайт «${s.name}» из справочника?`)) return;
        await api(`/api/sites/${s.id}`, { method: "DELETE" });
        await loadSiteDirectory();
      };
    }
    box.appendChild(row);
  });
}

function updateSiteTypeUI() {
  const type = $("#sType").value;
  if (type === "xenforo") {
    $("#sUrlLabelText").textContent = "Адрес форума (без /search, просто корень сайта)";
    $("#sUrlLabelCode").classList.add("hidden");
    $("#sUrlLabelTail").classList.add("hidden");
    $("#sUrlTemplate").placeholder = "https://example-forum.com";
    $("#sTypeHint").textContent = "Сразу идёт по цепочке XenForo (токен → POST → результаты), без первой попытки обычной ссылки — быстрее, если сайт точно на XenForo.";
  } else {
    $("#sUrlLabelText").textContent = "Шаблон поисковой ссылки (с плейсхолдером";
    $("#sUrlLabelCode").classList.remove("hidden");
    $("#sUrlLabelTail").classList.remove("hidden");
    $("#sUrlTemplate").placeholder = "https://example-forum.ru/search/?q={query}";
    $("#sTypeHint").textContent = "В режиме «Автоматически» можно вставить и обычный шаблон с {query}, и просто адрес сайта — сработает то, что подходит.";
  }
}
$("#sType").onchange = updateSiteTypeUI;

function openSiteModal(site) {
  editingSiteId = site ? site.id : null;
  $("#siteModalTitle").textContent = site ? "Изменить сайт" : "Новый сайт";
  $("#sName").value = site?.name || "";
  $("#sUrlTemplate").value = site?.url_template || "";
  $("#sType").value = site?.type || "generic";
  $("#sMode").value = siteModeOf(site || {});
  $("#sPriority").value = site?.priority || "normal";
  $("#sMirrors").value = (site?.mirrors || []).join("\n");
  $("#sNotes").value = site?.notes || "";
  updateSiteTypeUI();
  $("#siteModalOverlay").classList.remove("hidden");
}
$("#newSiteBtn").onclick = () => openSiteModal(null);
$("#cancelSiteBtn").onclick = () => $("#siteModalOverlay").classList.add("hidden");
$("#saveSiteBtn").onclick = async () => {
  const mode = $("#sMode").value;
  // старое поле «тип» выводится из режима — для совместимости со старым кодом
  const type = mode === "xenforo" ? "xenforo" : (mode === "template" ? "generic" : "auto");
  const payload = {
    name: $("#sName").value.trim(), url_template: $("#sUrlTemplate").value.trim(), type,
    mode, priority: $("#sPriority").value, notes: $("#sNotes").value.trim(),
    mirrors: $("#sMirrors").value.split("\n").map((x) => x.trim()).filter(Boolean),
  };
  if (mode === "template" && !payload.url_template.includes("{query}")) { alert("Для режима «только по шаблону» в адресе нужен {query}"); return; }
  if (!payload.name || !payload.url_template) { alert("Заполните название и адрес/шаблон ссылки"); return; }
  if (type === "generic" && !payload.url_template.includes("{query}")) { alert("В шаблоне ссылки должен быть {query}"); return; }
  try {
    if (editingSiteId) {
      await api(`/api/sites/${editingSiteId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      await api("/api/sites", { method: "POST", body: JSON.stringify(payload) });
    }
  } catch (e) {
    alert("Ошибка: " + e.message);
    return;
  }
  $("#siteModalOverlay").classList.add("hidden");
  await loadSiteDirectory();
};

let currentSiteSearchJobId = null;

$("#siteSearchShowNegKeywords").onchange = (e) => {
  $("#siteSearchNegKeywords").classList.toggle("hidden", !e.target.checked);
};

$("#siteSearchRunBtn").onclick = async () => {
  const queries = $("#siteSearchQuery").value.split("\n").map((q) => q.trim()).filter(Boolean);
  if (!queries.length) { alert("Введите хотя бы один запрос (по одному на строку)"); return; }
  if (!state.sites.length) { alert("Добавьте хотя бы один сайт в справочник"); return; }
  const negative_keywords = $("#siteSearchShowNegKeywords").checked
    ? $("#siteSearchNegKeywords").value.split("\n").map((s) => s.trim()).filter(Boolean)
    : [];

  $("#siteSearchProgress").classList.remove("hidden");
  $("#siteSearchErrors").classList.add("hidden");
  $("#siteResultsBlock").classList.add("hidden");
  $("#siteProgressFill").style.width = "2%";
  const queriesLabel = queries.length === 1 ? `«${queries[0]}»` : `${queries.length} вариантов запроса`;
  $("#siteProgressLabel").textContent = `Запуск поиска ${queriesLabel} на ${state.sites.length} сайт(ах)…`;
  $("#siteSearchRunBtn").disabled = true;
  $("#stopSiteSearchBtn").disabled = false;

  let started;
  try {
    started = await api("/api/sites/search", { method: "POST", body: JSON.stringify({ queries, negative_keywords }) });
  } catch (e) {
    $("#siteSearchProgress").classList.add("hidden");
    $("#siteSearchRunBtn").disabled = false;
    alert("Ошибка поиска: " + e.message);
    return;
  }

  currentSiteSearchJobId = started.job_id;
  $("#siteSearchBtn").textContent = "🔎 Поиск по сайтам (идёт…)";
  pollSiteSearchJob(started.job_id);
};

$("#stopSiteSearchBtn").onclick = async () => {
  if (!currentSiteSearchJobId) return;
  $("#stopSiteSearchBtn").disabled = true;
  try {
    await api(`/api/sites/search-jobs/${currentSiteSearchJobId}/cancel`, { method: "POST" });
  } catch (e) {
    alert("Не удалось остановить поиск: " + e.message);
    $("#stopSiteSearchBtn").disabled = false;
  }
};

function pollSiteSearchJob(jobId) {
  const interval = setInterval(async () => {
    let job;
    try {
      job = await api(`/api/sites/search-jobs/${jobId}`);
    } catch (e) {
      clearInterval(interval);
      $("#siteSearchProgress").classList.add("hidden");
      $("#siteSearchRunBtn").disabled = false;
      $("#siteSearchBtn").textContent = "🔎 Поиск по сайтам";
      currentSiteSearchJobId = null;
      alert("Ошибка при опросе статуса поиска: " + e.message);
      return;
    }

    const p = job.progress || { done: 0, total: 1, current_site: "" };
    const pct = Math.max(2, Math.round((p.done / Math.max(p.total, 1)) * 100));
    $("#siteProgressFill").style.width = pct + "%";
    $("#siteProgressLabel").textContent = p.current_site
      ? `Проверено ${p.done} из ${p.total} — сейчас: ${p.current_site}`
      : `Проверено ${p.done} из ${p.total}…`;

    if (job.status === "done" || job.status === "cancelled") {
      clearInterval(interval);
      $("#siteProgressFill").style.width = job.status === "done" ? "100%" : pct + "%";
      $("#siteSearchRunBtn").disabled = false;
      $("#stopSiteSearchBtn").disabled = false;
      $("#siteSearchBtn").textContent = "🔎 Поиск по сайтам";
      currentSiteSearchJobId = null;
      setTimeout(() => $("#siteSearchProgress").classList.add("hidden"), 300);

      const data = job.result;
      if (!data) return; // остановлено ещё до того, как что-либо успело найтись
      if (job.status === "cancelled") {
        $("#siteSearchErrors").classList.remove("hidden");
        $("#siteSearchErrors").textContent = "Поиск остановлен — показано то, что успели найти до остановки.";
      } else if (data.errors && data.errors.length) {
        $("#siteSearchErrors").classList.remove("hidden");
        $("#siteSearchErrors").innerHTML = "Не удалось получить результаты с некоторых сайтов:<br>" +
          data.errors.map((e) => `• <b>${escapeHtml(e.site)}</b>: ${escapeHtml(e.error)}`).join("<br>");
      }
      renderSiteRedirects(data.redirects || []);
      renderSiteReport(data);
      renderSiteResults(data.results);
      loadSiteDirectory();  // обновить статусы сайтов в справочнике
    } else if (job.status === "error") {
      clearInterval(interval);
      $("#siteSearchProgress").classList.add("hidden");
      $("#siteSearchRunBtn").disabled = false;
      $("#siteSearchBtn").textContent = "🔎 Поиск по сайтам";
      currentSiteSearchJobId = null;
      alert("Ошибка поиска: " + (job.error || "неизвестная ошибка"));
    }
  }, 1000);
}

function renderSiteRedirects(redirects) {
  const box = $("#siteSearchRedirects");
  if (!redirects.length || !state.canEditSites) {
    // Без права редактировать справочник — предложение "Обновить адрес"
    // всё равно приведёт к 403 на сервере, только зря собьёт с толку.
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = "🔀 Похоже, эти сайты целиком переехали на другой домен — можно обновить адрес в справочнике одним кликом:<br>" +
    redirects.map((r) => `
      <div class="site-redirect-row">
        <span><b>${escapeHtml(r.site)}</b>: ${escapeHtml(r.old_domain)} → ${escapeHtml(r.new_domain)}</span>
        <button class="row-btn" data-site-id="${r.site_id}" data-new-domain="${escapeHtml(r.new_domain)}">Обновить адрес</button>
      </div>
    `).join("");

  box.querySelectorAll("button[data-site-id]").forEach((btn) => {
    btn.onclick = async () => {
      const siteId = btn.dataset.siteId;
      const newDomain = btn.dataset.newDomain;
      btn.disabled = true;
      btn.textContent = "Обновляю…";
      try {
        // отдельный обработчик переезда: меняет только домен, сохраняя путь
        // и {query}, а старый адрес добавляет в зеркала сайта
        await api(`/api/sites/${siteId}/apply-redirect`, {
          method: "POST",
          body: JSON.stringify({ new_domain: newDomain }),
        });
        btn.textContent = "Обновлено ✓";
        await loadSiteDirectory();
      } catch (e) {
        alert("Не удалось обновить адрес: " + e.message);
        btn.disabled = false;
        btn.textContent = "Обновить адрес";
      }
    };
  });
}

function renderSiteResults(results) {
  $("#siteResultsBlock").classList.remove("hidden");
  const body = $("#siteResultsBody");
  body.innerHTML = "";
  $("#siteNoResults").classList.toggle("hidden", results.length > 0);
  state.lastSiteResults = results;

  // Автор/произведение, выбранные сейчас в «Прикрепить к произведению» —
  // именно на этого автора ориентируется бейдж «уже постоянно
  // блокируется» ниже (тот же автор, что получит ссылку при «→ В
  // блокировку», см. комментарий у этой кнопки).
  const attachWorkId = $("#siteSearchAttachWork").value;
  const attachedAuthorName = attachWorkId ? (findWork(attachWorkId) || {}).author?.name : null;

  results.forEach((r) => {
    const tr = document.createElement("tr");
    if (r.already_in_blocking) tr.classList.add("row-already-blocked");

    const hostname = extractHostname(r.url);
    const baseDomain = siteSearchBaseDomain(hostname);
    const isKnownChronic = attachedAuthorName && (state.chronicGroups || []).some(
      (g) => g.author_name === attachedAuthorName && g.base_domain === baseDomain
    );
    const looksMirror = looksLikeMirrorSubdomain(hostname);
    const badges = [
      isKnownChronic ? `<span class="chronic-known-badge" title="Домен «${escapeHtml(baseDomain)}» уже постоянно блокируется у автора «${escapeHtml(attachedAuthorName)}»">⭐ уже хронический</span>` : "",
      looksMirror ? `<span class="mirror-pattern-badge" title="Поддомен «${escapeHtml(hostname.split(".")[0])}» — по виду типичное зеркало (буква+цифры), но история повторов ещё не набралась">🔁 похоже на сменщика</span>` : "",
    ].filter(Boolean).join(" ");

    tr.innerHTML = `
      <td><input type="checkbox" class="row-select-cb" data-url="${escapeHtml(r.url)}"></td>
      <td><span class="source-tag">${escapeHtml(r.source)}</span></td>
      <td class="r-title">${escapeHtml(r.title)}${r.already_in_blocking ? ' <span class="already-blocked-badge" title="Эта ссылка уже есть в таблице «Блокировка»">✓ уже добавлено</span>' : ""}${badges ? `<div class="site-result-badges">${badges}</div>` : ""}</td>
      <td><a class="r-url" href="${escapeHtml(r.url)}" target="_blank" rel="noopener">${escapeHtml(r.url)}</a></td>
      <td class="r-desc">${escapeHtml(r.matched_query || "")}</td>
      <td>
        <div class="row-actions">
          <button class="row-btn" data-act="copy">Копировать</button>
          <button class="row-btn" data-act="copy-url" title="Скопировать только ссылку, без названия и описания">Копировать ссылку</button>
          <button class="row-btn" data-act="attach">+ В сохранённые</button>
          ${r.already_in_blocking ? "" : '<button class="row-btn" data-act="block" title="Нужно сначала выбрать произведение в списке «Прикрепить к произведению» выше — автор и произведение берутся оттуда">→ В блокировку</button>'}
        </div>
      </td>
    `;
    tr.querySelector('[data-act="copy"]').onclick = (e) => copyRow({ title: r.title, url: r.url, description: "" }, e.currentTarget);
    tr.querySelector('[data-act="copy-url"]').onclick = (e) => copyUrlOnly(r, e.currentTarget);
    tr.querySelector('[data-act="attach"]').onclick = (e) => attachSiteResultToWork(r, e.currentTarget);
    const blockBtn = tr.querySelector('[data-act="block"]');
    if (blockBtn) {
      blockBtn.onclick = (e) => {
        // Раньше здесь в поле «Автор» ошибочно попадал текст поискового
        // запроса (r.matched_query), а не настоящее имя автора — например,
        // "GPT's агенты" (название произведения, использованное как
        // запрос) вместо "Андрианов Евгений Владимирович". Из-за этого в
        // таблице «Блокировка» появлялись лишние группы, названные текстом
        // запроса. Теперь автор и произведение берутся из выпадающего
        // списка «Прикрепить к произведению» — так же, как уже требуется
        // для кнопки «+ В сохранённые» (attachSiteResultToWork) — вместо
        // произвольного текста запроса.
        const workId = $("#siteSearchAttachWork").value;
        if (!workId) {
          alert("Сначала выберите произведение в списке выше «Прикрепить к произведению» — иначе непонятно, какому автору отнести ссылку.");
          return;
        }
        const found = findWork(workId);
        if (!found) {
          alert("Выбранное произведение не найдено — обновите страницу и попробуйте снова.");
          return;
        }
        sendToBlocking(
          { title: r.title, url: r.url, description: "", source: r.source },
          { author_name: found.author.name, work_title: found.work.title, work_id: workId },
          e.currentTarget
        );
      };
    }
    body.appendChild(tr);
  });
}

async function attachSiteResultToWork(r, btn) {
  const workId = $("#siteSearchAttachWork").value;
  if (!workId) {
    alert("Сначала выберите произведение в списке выше — к нему прикрепится результат.");
    return;
  }
  btn.disabled = true;
  const original = btn.textContent;
  try {
    await api(`/api/works/${workId}/results`, {
      method: "POST",
      body: JSON.stringify({ url: r.url, title: r.title, description: "", source: r.source || "Поиск по сайтам" }),
    });
    btn.textContent = "Добавлено ✓";
  } catch (e) {
    if (e.message.includes("уже есть")) {
      btn.textContent = "Уже добавлено";
    } else {
      alert("Не удалось добавить: " + e.message);
      btn.disabled = false;
      btn.textContent = original;
    }
  }
}

$("#siteExportCsvBtn").onclick = () => {
  const results = state.lastSiteResults || [];
  const header = "source,title,url,matched_query\n";
  const rows = results.map((r) => [r.source, r.title, r.url, r.matched_query].map((v) => `"${(v || "").replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob(["\ufeff" + header + rows], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "поиск_по_сайтам.csv";
  a.click();
};
$("#siteCopySelectedBtn").onclick = (e) => copySelectedUrls("siteResultsBody", e.currentTarget);

$("#siteSearchBtn").onclick = showSiteSearchView;

// ---------- документы автора ----------
let currentDocsAuthorId = null;

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " Б";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " КБ";
  return (bytes / (1024 * 1024)).toFixed(1) + " МБ";
}

function formatDocDate(ts) {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("ru-RU");
}

function formatIsoDateRu(isoDate) {
  // isoDate в формате YYYY-MM-DD (как из <input type="date">), не unix-таймстамп
  if (!isoDate) return "";
  const [y, m, d] = isoDate.split("-");
  return `${d}.${m}.${y}`;
}

function daysSince(isoDate) {
  // Целое число дней, прошедших с даты в формате YYYY-MM-DD — используется
  // для напоминаний вида «14 дней с подачи», не зависящих от того, успела
  // ли уже отработать фоновая автоматическая проверка (см. renderBlockingRow) —
  // если сервер был выключен именно в этот момент, фоновая проверка могла
  // не сработать вовремя, а это напоминание всё равно покажет честную цифру.
  if (!isoDate) return null;
  const then = new Date(isoDate + "T00:00:00");
  if (Number.isNaN(then.getTime())) return null;
  const now = new Date();
  return Math.floor((now - then) / 86400000);
}

async function openDocumentsModal(author) {
  currentDocsAuthorId = author.id;
  $("#documentsModalTitle").textContent = `Документы: ${author.name}`;
  $("#documentUploadForm").reset();
  // Загрузка/скачивание/удаление — только у admin (см. backend/app.py).
  // У сотрудника с временным разрешением — только просмотр (см. renderDocumentsList).
  const isAdmin = !state.authEnabled || state.role === "admin";
  $("#documentUploadForm").classList.toggle("hidden", !isAdmin);
  $("#documentsModalOverlay").classList.remove("hidden");
  await loadDocuments();
}

async function loadDocuments() {
  const docs = await api(`/api/authors/${currentDocsAuthorId}/documents`);
  renderDocumentsList(docs);
}

function renderDocumentsList(docs) {
  const isAdmin = !state.authEnabled || state.role === "admin";
  const box = $("#documentsList");
  box.innerHTML = "";
  $("#documentsEmptyMsg").classList.toggle("hidden", docs.length > 0);
  docs.forEach((d) => {
    const row = document.createElement("div");
    row.className = "document-row";
    row.innerHTML = `
      <div class="document-row-info">
        <div class="document-row-name"><span class="document-type-badge">${escapeHtml(d.doc_type)}</span>${escapeHtml(d.original_name)}</div>
        <div class="document-row-meta">${formatFileSize(d.size)} · ${formatDocDate(d.uploaded_at)}${d.description ? " · " + escapeHtml(d.description) : ""}</div>
      </div>
      <div class="document-row-actions">
        <a class="row-btn" href="/api/authors/${currentDocsAuthorId}/documents/${d.id}/view" target="_blank" rel="noopener">Просмотреть</a>
        ${isAdmin ? `<a class="row-btn" href="/api/authors/${currentDocsAuthorId}/documents/${d.id}/download">Скачать</a>` : ""}
        ${isAdmin ? `<button class="row-btn danger" data-act="del">Удалить</button>` : ""}
      </div>
    `;
    if (isAdmin) {
      row.querySelector('[data-act="del"]').onclick = async () => {
        if (!confirm(`Удалить документ «${d.original_name}»? Отменить нельзя.`)) return;
        await api(`/api/authors/${currentDocsAuthorId}/documents/${d.id}`, { method: "DELETE" });
        await loadDocuments();
      };
    }
    box.appendChild(row);
  });
}

$("#documentUploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = $("#docFile");
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("doc_type", $("#docType").value);
  formData.append("description", $("#docDescription").value.trim());

  const btn = $("#docUploadBtn");
  btn.disabled = true;
  btn.textContent = "Загрузка…";
  try {
    const res = await fetch(`/api/authors/${currentDocsAuthorId}/documents`, { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${res.status}`);
    }
    $("#documentUploadForm").reset();
    await loadDocuments();
  } catch (err) {
    alert("Не удалось загрузить: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Загрузить";
  }
});

$("#closeDocumentsBtn").onclick = () => $("#documentsModalOverlay").classList.add("hidden");

// ---------- мои документы (доверенность от фирмы и т.п.) ----------
$("#myDocumentsBtn").onclick = async () => {
  $("#myDocumentUploadForm").reset();
  $("#myDocumentsModalOverlay").classList.remove("hidden");
  await loadMyDocuments();
};

async function loadMyDocuments() {
  const docs = await api("/api/me/documents");
  renderMyDocumentsList(docs);
}

function renderMyDocumentsList(docs) {
  const box = $("#myDocumentsList");
  box.innerHTML = "";
  $("#myDocumentsEmptyMsg").classList.toggle("hidden", docs.length > 0);
  docs.forEach((d) => {
    const row = document.createElement("div");
    row.className = "document-row";
    row.innerHTML = `
      <div class="document-row-info">
        <div class="document-row-name">${escapeHtml(d.original_name)}</div>
        <div class="document-row-meta">${formatFileSize(d.size)} · ${formatDocDate(d.uploaded_at)}${d.description ? " · " + escapeHtml(d.description) : ""}</div>
      </div>
      <div class="document-row-actions">
        <a class="row-btn" href="/api/me/documents/${d.id}/download">Скачать</a>
        <button class="row-btn danger" data-act="del">Удалить</button>
      </div>
    `;
    row.querySelector('[data-act="del"]').onclick = async () => {
      if (!confirm(`Удалить документ «${d.original_name}»? Отменить нельзя.`)) return;
      await api(`/api/me/documents/${d.id}`, { method: "DELETE" });
      await loadMyDocuments();
    };
    box.appendChild(row);
  });
}

$("#myDocumentUploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = $("#myDocFile");
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("description", $("#myDocDescription").value.trim());

  const btn = $("#myDocUploadBtn");
  btn.disabled = true;
  btn.textContent = "Загрузка…";
  try {
    const res = await fetch("/api/me/documents", { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${res.status}`);
    }
    $("#myDocumentUploadForm").reset();
    await loadMyDocuments();
  } catch (err) {
    alert("Не удалось загрузить: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Загрузить";
  }
});

$("#closeMyDocumentsBtn").onclick = () => $("#myDocumentsModalOverlay").classList.add("hidden");

// ---------- скриншоты по делу блокировки ----------
let currentShotsCaseId = null;
const IMAGE_EXT_RE = /\.(jpe?g|png|webp|gif)$/i;

async function openScreenshotsModal(c) {
  currentShotsCaseId = c.id;
  $("#screenshotsModalTitle").textContent = `Скриншоты: ${c.title}`;
  $("#screenshotsModalUrl").textContent = c.url;
  $("#screenshotUploadForm").reset();
  $("#screenshotsModalOverlay").classList.remove("hidden");
  await loadScreenshots();
}

async function loadScreenshots() {
  const shots = await api(`/api/blocking-cases/${currentShotsCaseId}/screenshots`);
  renderScreenshotsGrid(shots);
  // обновим счётчик в таблице без полной перезагрузки
  const caseObj = state.blockingCases.find((x) => x.id === currentShotsCaseId);
  if (caseObj) {
    caseObj.screenshots_count = shots.length;
    refreshActiveBlockingLikeView();
  }
}

function renderScreenshotsGrid(shots) {
  const grid = $("#screenshotsGrid");
  grid.innerHTML = "";
  $("#screenshotsEmptyMsg").classList.toggle("hidden", shots.length > 0);
  shots.forEach((s) => {
    const card = document.createElement("div");
    card.className = "screenshot-card";
    const isImage = IMAGE_EXT_RE.test(s.original_name);
    const previewUrl = `/api/blocking-cases/${currentShotsCaseId}/screenshots/${s.id}/file`;
    card.innerHTML = `
      ${isImage
        ? `<a href="${previewUrl}" target="_blank" rel="noopener"><img class="screenshot-thumb" src="${previewUrl}" alt=""></a>`
        : `<a class="screenshot-thumb screenshot-thumb-file" href="${previewUrl}" target="_blank" rel="noopener">📄 PDF</a>`}
      <div class="screenshot-card-meta">
        <div class="document-row-meta">${formatFileSize(s.size)} · ${formatDocDate(s.uploaded_at)}</div>
        ${s.purpose === "defendant_proof" ? '<div class="document-row-meta">🏢 Подтверждение хостинга/ответчика</div>' : ""}
        ${s.source === "auto" ? `<div class="document-row-meta">📸 Автоснимок · ${escapeHtml(s.captured_url || "")}</div>` : ""}
        ${s.description ? `<div class="document-row-meta">${escapeHtml(s.description)}</div>` : ""}
        <div class="document-row-actions">
          <a class="row-btn" href="/api/blocking-cases/${currentShotsCaseId}/screenshots/${s.id}/download">Скачать</a>
          ${s.html_filename ? `<a class="row-btn" href="/api/blocking-cases/${currentShotsCaseId}/screenshots/${s.id}/html">HTML</a>` : ""}
          <button class="row-btn danger" data-act="del">Удалить</button>
        </div>
      </div>
    `;
    card.querySelector('[data-act="del"]').onclick = async () => {
      if (!confirm("Удалить этот скриншот? Отменить нельзя.")) return;
      await api(`/api/blocking-cases/${currentShotsCaseId}/screenshots/${s.id}`, { method: "DELETE" });
      await loadScreenshots();
    };
    grid.appendChild(card);
  });
}

$("#screenshotUploadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = $("#shotFile");
  if (!fileInput.files.length) return;

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("description", $("#shotDescription").value.trim());
  formData.append("purpose", $("#shotPurpose").value);

  const btn = $("#shotUploadBtn");
  btn.disabled = true;
  btn.textContent = "Загрузка…";
  try {
    const res = await fetch(`/api/blocking-cases/${currentShotsCaseId}/screenshots`, { method: "POST", body: formData });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${res.status}`);
    }
    $("#screenshotUploadForm").reset();
    await loadScreenshots();
  } catch (err) {
    alert("Не удалось загрузить: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Загрузить";
  }
});

$("#closeScreenshotsBtn").onclick = () => $("#screenshotsModalOverlay").classList.add("hidden");

// ---------- «Другие» обращения (несколько записей на дело, произвольная площадка) ----------
let currentOtherComplaintsCaseId = null;
let currentOtherComplaintsCase = null;

// Официальные формы/адреса для жалоб на популярных площадках. У всех, кроме
// Telegram, есть настоящая веб-форма — открываем её в новой вкладке, заполнение
// оставляем человеку (это подписанное юридическое заявление с входом в
// аккаунт, автоматизировать его нельзя и не нужно, тот же принцип, что и
// с формой Google DMCA). У Telegram официальной веб-формы нет вообще —
// единственный задокументированный канал это письмо на dmca@telegram.org,
// поэтому открываем черновик письма с уже подставленной ссылкой на нарушение.
const PLATFORM_COMPLAINT_INFO = {
  // У Google, в отличие от остальных площадок этого списка, форма не
  // привязана к конкретному URL-параметру — просто открывает общую форму
  // поиска DMCA, заполняется полностью вручную, как и было раньше в
  // отдельном фиксированном блоке (см. заметку разработки, 03.09 — Google
  // теперь просто ещё один пункт этого списка, без отдельного жёсткого
  // блока в разметке).
  google: { label: "Google DMCA", url: "https://reportcontent.google.com/forms/dmca_search?pli=1" },
  vk: { label: "VK / VK Видео", url: "https://vk.com/dmca" },
  youtube: { label: "YouTube", url: "https://www.youtube.com/copyright_complaint_form/" },
  instagram: { label: "Instagram", url: "https://help.instagram.com/contact/552695131608132" },
  facebook: { label: "Facebook", url: "https://www.facebook.com/help/contact/copyrightform" },
  telegram: { label: "Telegram", email: "dmca@telegram.org" },
  // Честная оговорка (как и раньше, когда у Avito был отдельный
  // механизм): официально задокументированного отдельного канала именно
  // для жалоб на авторские права у Avito не найдено — support.avito.ru/request
  // это общая форма поддержки, её надёжность как способа подачи именно
  // такой жалобы не проверена напрямую.
  avito: { label: "Avito", url: "https://support.avito.ru/request" },
};

function updateOtherComplaintFormFields() {
  const platform = $("#ocPlatform").value;
  const info = PLATFORM_COMPLAINT_INFO[platform];
  $("#ocMethodCustomLabel").classList.toggle("hidden", platform !== "other");
  const openBtn = $("#ocOpenFormBtn");
  if (info) {
    openBtn.classList.remove("hidden");
    openBtn.textContent = info.url ? `Открыть форму жалобы ↗ (${info.label})` : `Открыть письмо на ${info.email} ↗`;
  } else {
    openBtn.classList.add("hidden");
  }
}
$("#ocPlatform").addEventListener("change", updateOtherComplaintFormFields);

$("#ocOpenFormBtn").onclick = () => {
  const info = PLATFORM_COMPLAINT_INFO[$("#ocPlatform").value];
  if (!info) return;
  const c = currentOtherComplaintsCase;
  if (info.url) {
    window.open(info.url, "_blank", "noopener");
  } else if (info.email) {
    const subject = encodeURIComponent(`Жалоба на нарушение авторских прав — ${c?.work_title || ""}`);
    const body = encodeURIComponent(
      `Ссылка на нарушение: ${c?.url || ""}\nАвтор/правообладатель: ${c?.author_name || ""}\nПроизведение: ${c?.work_title || ""}\n\n`
    );
    window.open(`mailto:${info.email}?subject=${subject}&body=${body}`, "_blank");
  }
  // Открытие формы/письма — не то же самое, что фактическая отправка
  // жалобы, поэтому дату всё равно нужно проставить вручную после того,
  // как форма реально заполнена и отправлена.
};

async function openOtherComplaintsModal(c) {
  currentOtherComplaintsCaseId = c.id;
  currentOtherComplaintsCase = c;
  $("#otherComplaintsModalTitle").textContent = `Жалобы: ${c.title}`;
  $("#otherComplaintsModalUrl").textContent = c.url;
  $("#otherComplaintForm").reset();
  updateOtherComplaintFormFields();
  $("#otherComplaintsModalOverlay").classList.remove("hidden");
  renderOtherComplaintsList(c.other_complaints || []);
}

function renderOtherComplaintsList(entries) {
  const body = $("#otherComplaintsBody");
  body.innerHTML = "";
  $("#otherComplaintsEmptyMsg").classList.toggle("hidden", entries.length > 0);
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="r-num">${formatIsoDateRu(e.filed_at)}</td>
      <td><b>${escapeHtml(e.method)}</b></td>
      <td class="r-desc">${escapeHtml(e.notes || "")}</td>
      <td><input type="date" data-act="resolved" value="${escapeHtml(e.resolved_at || "")}" title="Когда площадка удалила ссылку"></td>
      <td><button class="row-btn danger" data-act="del">Удалить</button></td>
    `;
    tr.querySelector('[data-act="resolved"]').onchange = async (ev) => {
      try {
        const updated = await api(`/api/blocking-cases/${currentOtherComplaintsCaseId}/other-complaints/${e.id}`,
          { method: "PATCH", body: JSON.stringify({ resolved_at: ev.target.value }) });
        applyOtherComplaintsUpdate(updated);
      } catch (err) { alert("Не удалось сохранить дату: " + err.message); }
    };
    tr.querySelector('[data-act="del"]').onclick = async () => {
      if (!confirm(`Удалить запись «${e.method}» от ${formatIsoDateRu(e.filed_at)}? Отменить нельзя.`)) return;
      const updated = await api(`/api/blocking-cases/${currentOtherComplaintsCaseId}/other-complaints/${e.id}`, { method: "DELETE" });
      applyOtherComplaintsUpdate(updated);
    };
    body.appendChild(tr);
  });
}

function applyOtherComplaintsUpdate(updatedCase) {
  // обновляет и модальное окно, и счётчик в самой таблице, без полной перезагрузки
  renderOtherComplaintsList(updatedCase.other_complaints || []);
  const caseObj = state.blockingCases.find((x) => x.id === currentOtherComplaintsCaseId);
  if (caseObj) {
    caseObj.other_complaints = updatedCase.other_complaints;
    refreshActiveBlockingLikeView();
  }
}

$("#otherComplaintForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const platform = $("#ocPlatform").value;
  const info = PLATFORM_COMPLAINT_INFO[platform];
  const method = info ? info.label : $("#ocMethod").value.trim();
  if (!method) { alert("Укажите площадку"); return; }
  const btn = $("#ocAddBtn");
  btn.disabled = true;
  btn.textContent = "Добавление…";
  try {
    const updated = await api(`/api/blocking-cases/${currentOtherComplaintsCaseId}/other-complaints`, {
      method: "POST",
      body: JSON.stringify({
        filed_at: $("#ocFiledAt").value,
        method,
        notes: $("#ocNotes").value.trim(),
        resolved_at: $("#ocResolvedAt").value,
      }),
    });
    $("#otherComplaintForm").reset();
    updateOtherComplaintFormFields();
    applyOtherComplaintsUpdate(updated);
  } catch (err) {
    alert("Не удалось добавить: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Добавить";
  }
});

$("#closeOtherComplaintsBtn").onclick = () => $("#otherComplaintsModalOverlay").classList.add("hidden");

// ---------- личные данные автора-истца (полный доступ — admin; просмотр — по временному разрешению) ----------
let currentAuthorDataId = null;

let currentAuthorDataAuthorName = "";

async function openAuthorDataModal(author) {
  currentAuthorDataId = author.id;
  currentAuthorDataAuthorName = author.name;
  $("#authorDataModalTitle").textContent = `Личные данные: ${author.name}`;
  $("#authorDataForm").reset();
  $("#downloadAuthorReportLink").href = "#";
  $("#downloadAuthorReportLink").onclick = (ev) => { ev.preventDefault(); openClientReportModal(author.id); };
  const isAdmin = !state.authEnabled || state.role === "admin";
  // Редактирование — только admin (см. backend/app.py: PUT остался admin-only).
  // Держатель временного разрешения видит поля, но не может их менять.
  $("#authorDataForm").querySelectorAll("input, select").forEach((el) => { el.disabled = !isAdmin; });
  $("#aSaveBtn").classList.toggle("hidden", !isAdmin);
  $("#aSameAsRepresentativeBtn").classList.toggle("hidden", !isAdmin);
  $("#downloadAuthorReportLink").classList.toggle("hidden", !isAdmin);
  $("#authorDataModalOverlay").classList.remove("hidden");
  try {
    const fields = await api(`/api/authors/${author.id}/personal-data`);
    $("#aEntityType").value = fields.entity_type || "individual";
    $("#aFullName").value = fields.full_name || "";
    $("#aBirthPlace").value = fields.birth_place || "";
    $("#aPassport").value = fields.passport || "";
    $("#aIssuedBy").value = fields.issued_by || "";
    $("#aSnils").value = fields.snils || "";
    $("#aOrgName").value = fields.org_name || "";
    $("#aOrgInn").value = fields.org_inn || "";
    $("#aOrgKpp").value = fields.org_kpp || "";
    $("#aOrgAddress").value = fields.org_address || "";
    $("#aOrgRepresentative").value = fields.org_representative || "";
    $("#aCustomerName").value = fields.customer_name || "";
    $("#aCustomerDirector").value = fields.customer_director || "";
    $("#aContractNumber").value = fields.contract_number || "";
    $("#aContractDate").value = fields.contract_date || "";
    $("#aMonthlyFee").value = fields.monthly_fee || "";
    updateEntityTypeFieldsVisibility();
  } catch (e) {
    alert("Не удалось загрузить: " + e.message);
  }
}

function updateEntityTypeFieldsVisibility() {
  const entityType = $("#aEntityType").value;
  const isIndividual = entityType === "individual";
  $("#aIndividualFields").classList.toggle("hidden", !isIndividual);
  $("#aOrgFields").classList.toggle("hidden", isIndividual);
  // ИП и юрлицо используют один и тот же набор полей (свой ИНН есть у
  // обоих) — разница только в заголовке раздела заявления (petition.py),
  // подпись поля на экране тоже подстраиваем, чтобы не путать
  $("#aOrgNameLabel").firstChild.textContent = entityType === "individual_entrepreneur"
    ? "ФИО индивидуального предпринимателя " : "Наименование организации ";
}
$("#aEntityType").onchange = updateEntityTypeFieldsVisibility;

$("#aSameAsRepresentativeBtn").onclick = () => {
  // Пункт из запроса: иногда автор и есть руководитель организации/ИП —
  // не заставляем набирать одно и то же ФИО в трёх разных полях и
  // рисковать несовпадением из-за опечатки, копируем из имени автора.
  $("#aOrgRepresentative").value = currentAuthorDataAuthorName;
  $("#aCustomerDirector").value = currentAuthorDataAuthorName;
};

$("#closeAuthorDataBtn").onclick = () => $("#authorDataModalOverlay").classList.add("hidden");

// ---------- отдельный раздел: архив завершённых дел ----------
const MONTHS_RU_SHORT = ["", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

function showArchiveView() {
  state.activeWorkId = null;
  renderTree();
  hideAllViews();
  $("#archiveView").classList.remove("hidden");
  loadArchiveView();
}

async function loadArchiveView() {
  const body = $("#archiveBody");
  body.innerHTML = `<p class="hint-text">Загрузка…</p>`;
  let entries;
  try {
    entries = await api("/api/report-archive");
  } catch (err) {
    body.innerHTML = "";
    alert("Не удалось загрузить архив: " + err.message);
    return;
  }
  $("#archiveEmpty").classList.toggle("hidden", entries.length > 0);

  const byAuthor = new Map();
  entries.forEach((e) => {
    const name = e.author_name || "Без автора";
    if (!byAuthor.has(name)) byAuthor.set(name, []);
    byAuthor.get(name).push(e);
  });
  const authorNames = [...byAuthor.keys()].sort((a, b) => a.localeCompare(b, "ru"));

  // Сворачиваемая строка на каждого АВТОРА (не на каждую ссылку) — по
  // прямой просьбе пользователя: развернул одного автора — сразу видно
  // всю его работу по всем ссылкам одним блоком, не нужно кликать
  // по каждой ссылке отдельно.
  body.innerHTML = authorNames.map((name) => {
    const list = byAuthor.get(name).sort((a, b) => (b.archived_at || 0) - (a.archived_at || 0));
    return `
      <details class="archive-author-block">
        <summary><b>${escapeHtml(name)}</b> <span class="archive-author-count">— ${list.length}</span></summary>
        <table class="archive-links-table">
          <thead>
            <tr>
              <th>Ссылка / Произведение</th>
              <th>Дата претензии</th>
              <th>Обращения: МГС / РКН / статус</th>
              <th>Дата блокировки</th>
              <th>Архивировано</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${list.map((e) => `
              <tr data-id="${e.id}">
                <td>
                  <a class="r-url" href="${escapeHtml(e.url)}" target="_blank" rel="noopener" title="${escapeHtml(e.url)}">${escapeHtml(shortenUrl(e.url, 40))}</a>
                  <div class="hint-text">${escapeHtml(e.work_title || e.title || "")}</div>
                </td>
                <td>${e.claim_date ? formatIsoDateRu(e.claim_date) : "—"}</td>
                <td>${appealsSummaryHtml(e)}</td>
                <td>${e.block_date ? formatIsoDateRu(e.block_date) : "—"}</td>
                <td>
                  ${MONTHS_RU_SHORT[e.report_month] || ""} ${e.report_year || ""}
                  <div class="hint-text">${formatDocDate(e.archived_at)}</div>
                </td>
                <td><button type="button" class="row-btn" data-act="restore">Восстановить</button></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </details>
    `;
  }).join("");

  body.querySelectorAll('[data-act="restore"]').forEach((btn) => {
    btn.onclick = async () => {
      const tr = btn.closest("tr");
      const id = tr.dataset.id;
      const url = tr.querySelector(".r-url").href;
      if (!confirm(`Вернуть «${url}» обратно в активную таблицу «Блокировка»?`)) return;
      try {
        await api(`/api/report-archive/${id}/restore`, { method: "POST" });
        await loadArchiveView();
      } catch (err) {
        alert("Не удалось восстановить: " + err.message);
      }
    };
  });
}
$("#archiveBtn").onclick = showArchiveView;
$("#archiveRefreshBtn").onclick = loadArchiveView;

$("#authorDataForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = $("#aSaveBtn");
  btn.disabled = true;
  try {
    await api(`/api/authors/${currentAuthorDataId}/personal-data`, {
      method: "PUT",
      body: JSON.stringify({
        entity_type: $("#aEntityType").value,
        full_name: $("#aFullName").value.trim(),
        birth_place: $("#aBirthPlace").value.trim(),
        passport: $("#aPassport").value.trim(),
        issued_by: $("#aIssuedBy").value.trim(),
        snils: $("#aSnils").value.trim(),
        org_name: $("#aOrgName").value.trim(),
        org_inn: $("#aOrgInn").value.trim(),
        org_kpp: $("#aOrgKpp").value.trim(),
        org_address: $("#aOrgAddress").value.trim(),
        org_representative: $("#aOrgRepresentative").value.trim(),
        customer_name: $("#aCustomerName").value.trim(),
        customer_director: $("#aCustomerDirector").value.trim(),
        contract_number: $("#aContractNumber").value.trim(),
        contract_date: $("#aContractDate").value,
        monthly_fee: $("#aMonthlyFee").value.trim(),
      }),
    });
    $("#authorDataModalOverlay").classList.add("hidden");
  } catch (err) {
    alert("Не удалось сохранить: " + err.message);
  } finally {
    btn.disabled = false;
  }
});

// ---------- панель действий над выбранными ссылками: заявление в суд ИЛИ выгрузка в РКН ----------
// Один общий чекбокс выбора на каждую строку (первая колонка) — вместо
// прежних двух раздельных наборов (для заявления и для РКН) сотрудник
// один раз отмечает нужные ссылки, а дальше сам решает, какое действие
// сделать с выбором: подготовить заявление или скачать список для РКН.
// Панель показывает оба действия сразу, но «Подготовить заявление»
// становится недоступной, если выбор не годится для заявления (см.
// isPetitionEligible) — этому действию нужны более строгие условия
// (один автор, дела ещё не «закрыты»), тогда как выгрузка для РКН
// принимает любые выбранные ссылки как есть.
const SELECTION_BARS = [
  { bar: "blockingSelectionActionBar", info: "blockingSelectionInfo", petitionBtn: "preparePetitionBtn" },
];

function updateBlockingSelectionActionBar() {
  const n = state.blockingSelection.size;
  const selectedCases = getBlockingSelectedCases();
  const petitionCases = selectedCases.filter(isPetitionEligible);
  const petitionAuthors = new Set(petitionCases.map((c) => c.author_name || "Без автора"));

  SELECTION_BARS.forEach(({ bar: barId, info: infoId, petitionBtn: btnId }) => {
    const bar = $("#" + barId);
    if (!bar) return;
    if (n === 0) {
      bar.classList.add("hidden");
      return;
    }
    bar.classList.remove("hidden");
    $("#" + infoId).textContent = `Выбрано ссылок: ${n}`;

    const preparePetitionBtn = $("#" + btnId);
    if (petitionCases.length === 0) {
      preparePetitionBtn.disabled = true;
      preparePetitionBtn.title = "Среди выбранного нет дел, подходящих для заявления — заявление не требуется (уже заблокировано) или уже подано";
    } else if (petitionAuthors.size > 1) {
      preparePetitionBtn.disabled = true;
      preparePetitionBtn.title = "Среди выбранного — дела разных авторов, заявление можно собрать только по одному автору за раз";
    } else {
      preparePetitionBtn.disabled = false;
      preparePetitionBtn.title = petitionCases.length === n
        ? `В заявление войдут все ${n} выбранных (автор: ${[...petitionAuthors][0]})`
        : `В заявление войдёт ${petitionCases.length} из ${n} выбранных — остальные для заявления не подходят (автор: ${[...petitionAuthors][0]})`;
    }
  });
}

// Раньше выбирала между "Блокировкой" и отдельным разделом "Постоянно
// блокируемые ссылки" (два разных рендера над одним и тем же выбором) —
// с 17.09.2026 второго раздела больше нет, оставлена как есть (не переименована),
// чтобы не трогать десяток мест, где она вызывается.
function refreshActiveBlockingLikeView() {
  renderBlockingTable();
}

function getBlockingSelectedCases() {
  return state.blockingCases.filter((c) => state.blockingSelection.has(c.id));
}

function downloadTextFile(filename, content, mime) {
  const blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function csvEscape(value) {
  return `"${String(value == null ? "" : value).replace(/"/g, '""')}"`;
}

function downloadRknTxt() {
  const cases = getBlockingSelectedCases();
  if (cases.length === 0) return;
  // Только сами ссылки, по одной на строку — именно так их проще всего
  // вставить/загрузить в форму на сайте РКН (eais.rkn.gov.ru), без лишних
  // данных, которые форма всё равно не примет.
  const text = cases.map((c) => c.url).join("\r\n");
  downloadTextFile(`rkn-ссылки-${new Date().toISOString().slice(0, 10)}.txt`, text);
}

function downloadRknCsv() {
  const cases = getBlockingSelectedCases();
  if (cases.length === 0) return;
  const header = ["Ссылка", "Ответчик", "IP-адрес", "№ определения Мосгорсуда", "Дата определения"];
  const lines = [header.map(csvEscape).join(";")];
  cases.forEach((c) => {
    lines.push([c.url, c.defendant || "", c.ip_address || "", c.court_ruling_number || "", c.court_ruling_date || ""].map(csvEscape).join(";"));
  });
  // \ufeff — BOM, чтобы Excel на Windows сразу правильно показал кириллицу
  downloadTextFile(`rkn-ссылки-${new Date().toISOString().slice(0, 10)}.csv`, "\ufeff" + lines.join("\r\n"), "text/csv;charset=utf-8");
}

$("#downloadRknExportTxtBtn").onclick = downloadRknTxt;
$("#downloadRknExportCsvBtn").onclick = downloadRknCsv;

$("#clearBlockingSelectionBtn").onclick = () => {
  state.blockingSelection.clear();
  refreshActiveBlockingLikeView();
};

async function preparePetitionHandler(btn) {
  const selectedCases = getBlockingSelectedCases().filter(isPetitionEligible);
  if (!selectedCases.length) return;
  const author = state.authors.find((a) => a.name === selectedCases[0].author_name);
  if (!author) {
    alert("Не удалось определить автора выбранных дел.");
    return;
  }

  // сначала показываем сотруднику личные данные автора для проверки —
  // это единственный момент, когда он вообще их видит, и он обязательно
  // фиксируется в журнале действий на бэкенде
  let fields;
  try {
    fields = await api(`/api/authors/${author.id}/personal-data/for-petition`);
  } catch (err) {
    alert("Не удалось получить данные автора: " + err.message);
    return;
  }
  const preview =
    `Проверьте данные истца перед подготовкой заявления — «${author.name}»:\n\n` +
    `ФИО, дата рождения: ${fields.full_name || "[не заполнено]"}\n` +
    `Место рождения: ${fields.birth_place || "[не заполнено]"}\n` +
    `Паспорт: ${fields.passport || "[не заполнено]"}\n` +
    `Кем выдан: ${fields.issued_by || "[не заполнено]"}\n` +
    `СНИЛС: ${fields.snils || "[не заполнено]"}\n\n` +
    `Если что-то неверно или устарело — отмените и попросите администратора поправить в карточке автора.\n\n` +
    `Продолжить и собрать заявление?`;
  if (!confirm(preview)) return;

  btn.disabled = true;
  const original = btn.textContent;
  btn.textContent = "Запускаю сборку заявления…";
  try {
    // Сборка теперь фоновая задача (см. backend/jobs.py) — при большом
    // числе дел/скриншотов это может занять заметное время, но сервер
    // при этом не блокируется для остальных пользователей, как раньше.
    const startRes = await fetch(`/api/authors/${author.id}/court-petition`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_ids: selectedCases.map((c) => c.id) }),
    });
    if (!startRes.ok) {
      const body = await startRes.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${startRes.status}`);
    }
    const { job_id } = await startRes.json();

    btn.textContent = "Собираю заявление и документы… (может занять некоторое время)";
    let status;
    let pollFailures = 0;
    do {
      await new Promise((r) => setTimeout(r, 1500));
      let pollRes;
      try {
        pollRes = await fetch(`/api/authors/${author.id}/court-petition/${job_id}`);
      } catch (netErr) {
        if (++pollFailures > 8) throw new Error("Сервер не отвечает — попробуйте ещё раз позже");
        continue;
      }
      const body = await pollRes.json().catch(() => null);
      if (body === null) {
        if (++pollFailures > 8) throw new Error(`Сервер вернул неожиданный ответ (${pollRes.status}) — попробуйте ещё раз позже`);
        continue;
      }
      pollFailures = 0;
      status = body.status;
      if (status === "error") throw new Error(body.error || "Не удалось подготовить заявление");
    } while (status !== "done");

    btn.textContent = "Скачиваю…";
    const downloadRes = await fetch(`/api/authors/${author.id}/court-petition/${job_id}/download`);
    if (!downloadRes.ok) {
      const body = await downloadRes.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${downloadRes.status}`);
    }
    const blob = await downloadRes.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `заявление_${author.name}.zip`;
    a.click();
    URL.revokeObjectURL(url);
    state.blockingSelection.clear();
    refreshActiveBlockingLikeView();
  } catch (err) {
    alert("Не удалось подготовить заявление: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
}
$("#preparePetitionBtn").onclick = () => preparePetitionHandler($("#preparePetitionBtn"));

$("#autoShotBtn").onclick = async () => {
  const btn = $("#autoShotBtn");
  btn.disabled = true;
  const original = btn.textContent;
  const caseId = currentShotsCaseId;
  try {
    btn.textContent = "Запускаю снимок…";
    const startRes = await fetch(`/api/blocking-cases/${caseId}/screenshots/capture`, { method: "POST" });
    if (!startRes.ok) {
      const body = await startRes.json().catch(() => ({}));
      throw new Error(body.error || `Ошибка ${startRes.status}`);
    }
    const { job_id } = await startRes.json();

    // опрашиваем статус фоновой задачи, не держим один долгий запрос —
    // так сервер (один рабочий процесс) не блокируется на всё время снимка
    btn.textContent = "Открываю страницу и делаю снимок… (может занять до 20 секунд)";
    let status;
    let pollFailures = 0;
    do {
      await new Promise((r) => setTimeout(r, 1200));
      let pollRes;
      try {
        pollRes = await fetch(`/api/blocking-cases/${caseId}/screenshots/capture/${job_id}`);
      } catch (netErr) {
        if (++pollFailures > 5) throw new Error("Сервер не отвечает — попробуйте ещё раз позже");
        continue;
      }
      // сервер иногда может ответить не JSON'ом, а HTML-страницей ошибки
      // (502/504 от nginx, если backend был на секунду перегружен во время
      // работы headless-браузера) — раньше это падало с непонятным
      // «Unexpected token '<'» вместо внятного сообщения
      const body = await pollRes.json().catch(() => null);
      if (body === null) {
        if (++pollFailures > 5) throw new Error(`Сервер вернул неожиданный ответ (${pollRes.status}) — попробуйте ещё раз позже`);
        continue;
      }
      pollFailures = 0;
      status = body.status;
      if (status === "error") throw new Error(body.error || "Не удалось сделать снимок");
      if (status === "done") {
        if (caseId === currentShotsCaseId) await loadScreenshots();
      }
    } while (status !== "done");
  } catch (err) {
    alert("Не удалось сделать автоматический скриншот: " + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = original;
  }
};

// ---------- Esc: закрыть текущее модальное окно, а если открытых нет —
// вернуться из карточки произведения к пустому экрану (по одному шагу
// на каждое нажатие, как в проводнике: сначала «выйти из текущего окна»,
// затем «вернуться на главный экран»). ----------
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const openOverlays = Array.from(document.querySelectorAll(".modal-overlay"))
    .filter((el) => !el.classList.contains("hidden"));
  if (openOverlays.length > 0) {
    // Последний в DOM-порядке — как правило, самое «верхнее» открытое окно
    // (окна не вкладываются друг в друга по-настоящему, поэтому это
    // разумное приближение «текущего», без переписывания каждого openXModal).
    openOverlays[openOverlays.length - 1].classList.add("hidden");
    return;
  }
  if (state.activeWorkId) {
    state.activeWorkId = null;
    state.activeAuthorId = null;
    showEmptyState();
  }
});

init();


// ---------- Отчёт для заказчика за период (обновление 23.09) ----------
function _isoDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

async function openClientReportModal(authorId) {
  if (!state.authors || !state.authors.length) {
    try { state.authors = await api("/api/authors"); } catch (e) { state.authors = []; }
  }
  const authorSel = $("#crAuthor");
  authorSel.innerHTML = `<option value="">Все авторы вместе</option>` +
    state.authors.map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join("");
  authorSel.value = authorId || "";
  $("#crFee").dataset.author = "";
  fillClientReportWorks();
  fillClientReportFee();
  const now = new Date();
  if (!$("#crFrom").value) $("#crFrom").value = _isoDate(new Date(now.getFullYear(), now.getMonth(), 1));
  if (!$("#crTo").value) $("#crTo").value = _isoDate(now);
  $("#clientReportModalOverlay").classList.remove("hidden");
}

function crSelectedAuthorIds() {
  const checked = [...document.querySelectorAll("#crWorks input[type=checkbox]:checked")];
  return [...new Set(checked.map((c) => c.dataset.author))];
}

async function fillClientReportFee() {
  // Стоимость показываем, когда в отчёте один автор: у каждого свой договор.
  const ids = $("#crAuthor").value ? [$("#crAuthor").value] : crSelectedAuthorIds();
  const authorId = ids.length === 1 ? ids[0] : "";
  $("#crFeeLabel").classList.toggle("hidden", !authorId);
  if ($("#crFee").dataset.author === authorId) return;  // не затирать исправленную сумму
  $("#crFee").value = "";
  $("#crFee").dataset.author = authorId;
  if (!authorId) return;
  try {
    const data = await api(`/api/authors/${authorId}/personal-data`);
    $("#crFee").value = ((data && (data.fields || data)) || {}).monthly_fee || "";
  } catch (e) { /* нет прав или данных — поле останется пустым */ }
}

function fillClientReportWorks() {
  // Список произведений с галочками: одного автора или всех авторов сразу
  // (сгруппировано по автору). По умолчанию отмечены все.
  const authorId = $("#crAuthor").value;
  const authors = (state.authors || []).filter((a) => !authorId || a.id === authorId);
  const box = $("#crWorks");
  box.innerHTML = authors.map((a) => {
    const works = (state.worksByAuthor || {})[a.id] || [];
    if (!works.length) return "";
    return `<div class="cr-works-author">${authorId ? "" : `<div class="cr-works-author-name">${escapeHtml(a.name)}</div>`}
      ${works.map((w) => `<label class="checkbox-inline-standalone"><input type="checkbox" checked data-work="${w.id}" data-author="${a.id}"> ${escapeHtml(w.title)}</label>`).join("")}
    </div>`;
  }).join("") || `<p class="hint-text">Нет произведений.</p>`;
  box.querySelectorAll("input[type=checkbox]").forEach((c) => { c.onchange = () => fillClientReportFee(); });
}

$("#crAuthor").onchange = () => { fillClientReportWorks(); fillClientReportFee(); };
$("#crAllWorks").onclick = () => { document.querySelectorAll("#crWorks input[type=checkbox]").forEach((c) => { c.checked = true; }); fillClientReportFee(); };
$("#crNoWorks").onclick = () => { document.querySelectorAll("#crWorks input[type=checkbox]").forEach((c) => { c.checked = false; }); fillClientReportFee(); };
$("#crCancelBtn").onclick = () => $("#clientReportModalOverlay").classList.add("hidden");
$("#crDownloadBtn").onclick = () => {
  const from = $("#crFrom").value, to = $("#crTo").value;
  if (!from || !to) { alert("Укажите период: с какого и по какое число"); return; }
  if (from > to) { alert("Дата «с» позже даты «по»"); return; }
  const params = new URLSearchParams({ date_from: from, date_to: to });
  const boxes = [...document.querySelectorAll("#crWorks input[type=checkbox]")];
  const checked = boxes.filter((c) => c.checked);
  if (!checked.length) { alert("Отметьте хотя бы одно произведение"); return; }
  if ($("#crAuthor").value) params.set("author_id", $("#crAuthor").value);
  // отмечены все — отчёт по автору (или всем авторам) целиком, включая
  // ссылки без распознанного произведения; иначе — только отмеченные
  if (checked.length < boxes.length) params.set("work_ids", checked.map((c) => c.dataset.work).join(","));
  if (!$("#crFeeLabel").classList.contains("hidden") && $("#crFee").value.trim()) params.set("fee", $("#crFee").value.trim());
  window.location.href = `/api/reports/protection.xlsx?${params.toString()}`;
  $("#clientReportModalOverlay").classList.add("hidden");
};
$("#openClientReportBtn").onclick = () => openClientReportModal("");
