(() => {
  'use strict';

  const STORAGE_KEY = 'nexcore-language';
  const supported = new Set(['ru', 'en']);
  const stored = localStorage.getItem(STORAGE_KEY);
  const language = supported.has(stored) ? stored : 'ru';

  if (!supported.has(stored)) localStorage.setItem(STORAGE_KEY, 'ru');
  document.documentElement.lang = language;

  const exact = new Map(Object.entries({
    'Nexcore — Hockey': 'Nexcore — Хоккей',
    'Nexcore hockey. Your team. Your collection. Your next great moment.': 'Nexcore Hockey. Твоя команда, твоя коллекция, твой следующий великий момент.',

    'Home': 'Главная',
    'Team': 'Состав',
    'Play': 'Играть',
    'Collection': 'Коллекция',
    'More': 'Ещё',
    'Back': 'Назад',
    'Profile': 'Профиль',
    'Inventory': 'Инвентарь',
    'Shop': 'Магазин',
    'Trades': 'Обмены',

    'Trade': 'Обмен',
    'Trade unavailable.': 'Обмен недоступен.',
    'Cancel offer': 'Отменить предложение',
    'From': 'От',
    'Creator gives': 'Автор предложения отдаёт',
    'Creator wants': 'Автор предложения хочет',
    'No cards': 'Нет карт',
    'No requested assets': 'Ничего не запрошено',
    'Could not load trade options': 'Не удалось загрузить варианты обмена',
    'Create trade': 'Создать обмен',
    'All assets are validated server-side': 'Все предметы проверяются сервером',
    'Target player': 'Получатель',
    'Public market': 'Публичный рынок',
    'Want cards': 'Хочу карты',
    'Want Coins': 'Хочу монеты',
    'You want': 'Ты хочешь',
    'Coins amount': 'Количество монет',
    'Publish trade': 'Опубликовать обмен',
    'SELECTED': 'ВЫБРАНО',
    'SELECT': 'ВЫБРАТЬ',
    'No tradeable cards.': 'Нет карт, доступных для обмена.',
    'Installed X-Factors stay attached to a traded card. Standalone X-Factor trade is not exposed here because the current production trade service has no standalone X-Factor offer storage.':
      'Установленные X-Факторы остаются привязаны к карте при обмене. Отдельный обмен X-Факторов здесь не показывается, потому что текущий production-сервис обменов не хранит отдельные предложения X-Факторов.',
    'Progress': 'Прогресс',
    'Clans': 'Кланы',
    'Creators': 'Авторы',
    'History': 'История',
    'Settings': 'Настройки',
    'Wallet': 'Кошелёк',
    'Account': 'Аккаунт',
    'Community': 'Сообщество',
    'Other': 'Другое',
    'Game': 'Игра',
    'ACCOUNT': 'АККАУНТ',
    'GAME': 'ИГРА',
    'COMMUNITY': 'СООБЩЕСТВО',
    'OTHER': 'ДРУГОЕ',

    'Quick match': 'Быстрый матч',
    'Clan war': 'Клановая война',
    'Events': 'События',
    'Event': 'Событие',
    'Creator tournaments': 'Турниры авторов',
    'Match': 'Матч',
    'Match complete': 'Матч завершён',
    'Match history': 'История матчей',
    'Match replay': 'Повтор матча',
    'Faceoff': 'Вбрасывание',
    'Final horn': 'Финальная сирена',
    'Moment': 'Момент',
    'Result': 'Результат',
    'Skip replay': 'Пропустить повтор',
    'Playing match…': 'Матч начинается…',
    'Match in progress · every simulator moment is shown over 30 seconds.': 'Матч идёт · все события симуляции показываются поэтапно за 30 секунд.',
    'BIG SAVE': 'БОЛЬШОЙ СЕЙВ',
    'POWER PLAY': 'БОЛЬШИНСТВО',
    'BIG HIT': 'СИЛОВОЙ ПРИЁМ',
    'BREAKAWAY': 'ВЫХОД 1 НА 1',
    'GOAL': 'ГОЛ',
    'X-FACTOR': 'X-ФАКТОР',
    'Pre-match check': 'Проверка перед матчем',
    'Choose the indicated number to start the match.': 'Выбери указанное число, чтобы начать матч.',
    'Could not open the pre-match check.': 'Не удалось открыть проверку перед матчем.',
    'Match already in progress.': 'Матч уже идёт.',
    'Too fast. Wait a moment.': 'Слишком часто. Подожди немного.',
    'Check passed. Match starts…': 'Проверка пройдена. Матч начинается…',
    'Match unavailable': 'Матч недоступен',
    'Complete the pre-match check first.': 'Сначала пройди проверку перед матчем.',
    'The pre-match check expired. Try again.': 'Проверка устарела. Пройди её ещё раз.',
    'The pre-match check is invalid. Try again.': 'Проверка недействительна. Пройди её ещё раз.',
    'Wrong answer. Complete the pre-match check again.': 'Неверный ответ. Пройди проверку ещё раз.',
    'This pre-match check belongs to another mode. Try again.': 'Эта проверка относится к другому режиму. Пройди её ещё раз.',
    'No new match result.': 'Нет нового результата матча.',
    'No matches yet.': 'Матчей пока нет.',
    'Match not found': 'Матч не найден',
    'Your OVR': 'Твой OVR',
    'Opponent OVR': 'OVR соперника',
    'Opponent': 'Соперник',
    'Rating': 'Рейтинг',
    'Games': 'Матчи',
    'Wins': 'Победы',
    'Win rate': 'Процент побед',
    'WIN': 'ПОБЕДА',
    'LOSS': 'ПОРАЖЕНИЕ',
    'DRAW': 'НИЧЬЯ',

    'Your next great moment starts here.': 'Твой следующий великий момент начинается здесь.',
    'Server-verified normal match.': 'Обычный матч с серверной проверкой.',
    'Normal match · backend verified.': 'Обычный матч · проверяется сервером.',
    'One team. One game. All yours.': 'Одна команда. Один матч. Всё зависит от тебя.',
    'Stronger together.': 'Вместе сильнее.',
    'Something worth playing for.': 'Есть ради чего играть.',
    'Find your next challenge with the hockey community.': 'Найди следующий вызов вместе с хоккейным сообществом.',
    'The next chapter is coming.': 'Следующая глава уже скоро.',
    'No open registrations at the moment.': 'Сейчас нет открытых регистраций.',

    'Continue': 'Продолжить',
    'Hit the ice': 'Выйти на лёд',
    'Find your next star': 'Найти новую звезду',
    'Last on the ice': 'Последний матч',
    'All modes': 'Все режимы',
    'See all': 'Смотреть все',
    'LIVE TEAM': 'АКТИВНЫЙ СОСТАВ',
    'FIRESIDE': 'FIRESIDE',
    'DAILY': 'ЕЖЕДНЕВНО',
    'Ready to claim': 'Можно забрать',
    'Already claimed today': 'Сегодня уже получено',

    'Best available lineup selected': 'Выбран лучший доступный состав',
    'Lineup updated': 'Состав обновлён',
    'Auto build': 'Автосостав',
    'Clear lineup': 'Очистить состав',
    'Edit lineup': 'Изменить состав',
    'Done': 'Готово',
    'Choose a player': 'Выбери игрока',
    'Choose a player to replace.': 'Выбери игрока для замены.',
    'Change': 'Заменить',
    'Add': 'Добавить',
    'Remove': 'Убрать',
    'Empty': 'Пусто',
    'slots filled': 'слотов заполнено',

    'Find a player': 'Найти игрока',
    'Filter cards': 'Фильтр карт',
    'Your collection': 'Твоя коллекция',
    'Position': 'Позиция',
    'Sort by': 'Сортировка',
    'All': 'Все',
    'Rating': 'Рейтинг',
    'Name': 'Имя',
    'Show cards': 'Показать карты',
    'No matching cards. Try another player or filter.': 'Карты не найдены. Попробуй другое имя или фильтр.',
    'Card': 'Карта',
    'Card information': 'Информация о карте',
    'Not in lineup': 'Не в составе',
    'In your starting lineup': 'В стартовом составе',
    'View your team': 'Открыть состав',
    'Salary': 'Зарплата',
    'Background': 'Фон',
    'Card background': 'Фон карты',
    'Home ice': 'Домашний лёд',
    'Home ice background': 'Фон домашнего льда',
    'Use Home ice': 'Использовать «Домашний лёд»',
    'Use original artwork': 'Использовать оригинальный арт',
    'Home ice applied to this card': 'Фон «Домашний лёд» применён к этой карте',
    'Original artwork selected': 'Выбран оригинальный арт',
    'Preview background': 'Предпросмотр фона',
    'A place to call your own.': 'Место, которое можно назвать своим.',

    'X-Factors': 'X-Факторы',
    'X-Factor': 'X-Фактор',
    'Installed': 'Установлен',
    'Remove & destroy': 'Снять и уничтожить',
    'Remove and destroy': 'Снять и уничтожить',
    'Already installed on this card': 'Уже установлен на эту карту',
    'No copies in inventory': 'Нет копий в инвентаре',
    'Replace an X-Factor': 'Заменить X-Фактор',
    'Choose a compatible card': 'Выбери подходящую карту',
    'X-Factor removed': 'X-Фактор удалён',
    'X-Factor replaced': 'X-Фактор заменён',
    'No X-Factors installed.': 'X-Факторы не установлены.',
    'Choose a card first.': 'Сначала выбери карту.',
    'No compatible X-Factors in inventory.': 'В инвентаре нет подходящих X-Факторов.',
    'Installed X-Factors transfer with this card.': 'Установленные X-Факторы передаются вместе с этой картой.',
    'Installed X-Factors belong to this card copy and transfer with it in a trade.': 'Установленные X-Факторы привязаны к этой копии карты и передаются вместе с ней при обмене.',

    'Mastery': 'Мастерство',
    'The journey': 'Путь',
    'A legacy in the making.': 'Легенда создаётся прямо сейчас.',
    'Every game counts.': 'Каждый матч имеет значение.',
    'Reward collected. Keep building your legacy.': 'Награда получена. Продолжай строить свою легенду.',
    'Continue earning Mastery XP to unlock this reward.': 'Продолжай получать опыт мастерства, чтобы открыть эту награду.',
    'Exclusive Mastery X-Factor': 'Эксклюзивный X-Фактор мастерства',

    'Boxes': 'Ящики',
    'Box': 'Ящик',
    'View box': 'Открыть ящик',
    'Open': 'Открыть',
    'Buy': 'Купить',
    'Buy & open': 'Купить и открыть',
    'Open box': 'Открыть ящик',
    'Drop rates': 'Шансы выпадения',
    'Possible collections': 'Возможные коллекции',
    'Resources': 'Ресурсы',
    'Cards': 'Карты',
    'Owned': 'В наличии',
    'Event reward': 'Награда события',
    'No boxes available.': 'Нет доступных ящиков.',
    'Box not found.': 'Ящик не найден.',
    'Nexcore reward box': 'Ящик с наградами Nexcore',
    'Something great awaits.': 'Внутри тебя ждёт что-то отличное.',
    'Tap to reveal your rewards.': 'Нажми, чтобы открыть награды.',
    'Reveal': 'Открыть',
    'View rewards': 'Посмотреть награды',
    'Next reward': 'Следующая награда',
    'Rewards revealed': 'Награды открыты',
    'Back to inventory': 'Вернуться в инвентарь',
    'YOUR NEXT STAR': 'ТВОЯ НОВАЯ ЗВЕЗДА',
    'A LITTLE MORE POSSIBILITY': 'ЕЩЁ НЕМНОГО ВОЗМОЖНОСТЕЙ',
    'NEXCORE COLLECTION': 'КОЛЛЕКЦИЯ NEXCORE',

    'Season Pass': 'Сезонный пропуск',
    'Hockey Pass': 'Хоккейный пропуск',
    'Free': 'Бесплатно',
    'FREE': 'БЕСПЛАТНО',
    'Premium': 'Премиум',
    'PREMIUM': 'ПРЕМИУМ',
    'PREMIUM ACTIVE': 'ПРЕМИУМ АКТИВЕН',
    'FREE TRACK': 'БЕСПЛАТНАЯ ЛИНИЯ',
    'Two reward tracks.': 'Две линии наград.',
    'Free and Premium rewards are claimed only on the backend.': 'Бесплатные и премиум-награды выдаются только сервером.',
    'Unlock Premium · 400 Energy': 'Открыть Premium · 400 Energy',
    'Premium Season Pass': 'Премиум-сезонный пропуск',
    'Premium Season Pass already active': 'Премиум-сезонный пропуск уже активен',
    'Premium reward unavailable': 'Премиум-награда недоступна',
    'Free reward claimed': 'Бесплатная награда получена',
    'Premium reward claimed': 'Премиум-награда получена',
    'Reward unavailable': 'Награда недоступна',
    'Level reached.': 'Уровень достигнут.',
    'Reach this level to unlock the reward.': 'Достигни этого уровня, чтобы открыть награду.',
    'This level is unlocked.': 'Этот уровень открыт.',
    'Keep playing to reach this level.': 'Продолжай играть, чтобы достичь этого уровня.',
    'CLAIMED': 'ПОЛУЧЕНО',
    'Claim': 'Забрать',
    'Claimed': 'Получено',

    'Fireside Craft': 'Крафт Fireside',
    'Craft': 'Создать',
    'Craft complete': 'Крафт завершён',
    'Craft unavailable': 'Крафт недоступен',
    'Choose card to consume': 'Выбери карту для расхода',
    'Missing card': 'Не хватает карты',
    'Back to Craft': 'Вернуться к крафту',
    'Real material cards + collectibles': 'Реальные карты-материалы + коллектиблы',
    'No Fireside recipes available.': 'Нет доступных рецептов Fireside.',
    'Fireside Collectible': 'Коллектибл Fireside',
    'FIRESIDE COLLECTIBLE': 'КОЛЛЕКТИБЛ FIRESIDE',
    'Craft players': 'Создавать игроков',
    'Crafting rule': 'Правило крафта',
    'CRAFTING RULE': 'ПРАВИЛО КРАФТА',
    'Target OVR − 2 + Collectibles': 'Целевой OVR − 2 + коллектиблы',
    'Craft costs': 'Стоимость крафта',

    'Energy Store': 'Магазин Energy',
    'Energy': 'Energy',
    'Payment is manual for now': 'Пока оплата проводится вручную',
    'MANUAL CHECKOUT': 'РУЧНАЯ ОПЛАТА',
    'Buy Energy': 'Купить Energy',
    'Base price': 'Базовая цена',

    'Daily reward': 'Ежедневная награда',
    'Welcome back.': 'С возвращением.',
    'Claim reward': 'Забрать награду',
    'Claim today': 'Забрать сегодня',
    'Your next reward is waiting tomorrow.': 'Следующая награда будет ждать тебя завтра.',
    'Daily': 'Ежедневные',
    'Seasonal': 'Сезонные',
    'Quests': 'Задания',
    'Backend-tracked progress': 'Прогресс отслеживается сервером',
    'No active quests.': 'Нет активных заданий.',
    'Achievements': 'Достижения',
    'Lifetime server-tracked milestones': 'Постоянные достижения, отслеживаемые сервером',
    'Lifetime milestones. One-time rewards.': 'Постоянные достижения. Награда выдаётся один раз.',
    'Collector': 'Коллекционер',
    'Veteran': 'Ветеран',

    'HEROES': 'HEROES',
    'Heroes': 'HEROES',
    'Career paths': 'Карьерные истории',
    'Career progress in normal matches.': 'Прогресс карьеры идёт в обычных матчах.',
    '94 → 100 OVR · live career progress': '94 → 100 OVR · живой прогресс карьеры',
    'Open a career. Write a legacy.': 'Открой карьеру. Напиши легенду.',
    'Eight careers. Six chapters each.': 'Восемь карьер. По шесть глав в каждой.',
    'Open path · 100,000 Coins': 'Открыть историю · 100 000 монет',
    'Open path': 'Открыть историю',
    'Open story · 100,000 Coins': 'Открыть историю · 100 000 монет',
    'Open this career path': 'Открыть эту карьерную историю',
    'Story already open': 'История уже открыта',
    'Story cannot be opened': 'Историю нельзя открыть',
    'Complete all 6 chapters first': 'Сначала заверши все 6 глав',
    'Claim HEROES 100': 'Забрать HEROES 100',
    'Claim 100 OVR': 'Забрать 100 OVR',
    'Write the final page?': 'Написать финальную страницу?',
    'STORY COMPLETE': 'ИСТОРИЯ ЗАВЕРШЕНА',
    'LEGACY COMPLETE': 'ЛЕГЕНДА ЗАВЕРШЕНА',
    'Career book': 'Книга карьеры',
    'Career Chapters': 'Главы карьеры',
    'COMING SOON': 'СКОРО',
    'STORY OPEN': 'ИСТОРИЯ ОТКРЫТА',
    'IN PROGRESS': 'В ПРОЦЕССЕ',
    'COMPLETED': 'ЗАВЕРШЕНО',
    'LOCKED': 'ЗАКРЫТО',
    'OBJECTIVE': 'ЗАДАНИЕ',
    'Not in active lineup': 'Не в активном составе',
    'In active lineup': 'В активном составе',

    'Cursed Mirror': 'Проклятое зеркало',
    'CURSED MIRROR': 'ПРОКЛЯТОЕ ЗЕРКАЛО',
    'LIMITED HALLOWEEN EVENT': 'ОГРАНИЧЕННОЕ ХЭЛЛОУИНСКОЕ СОБЫТИЕ',
    'LIVE': 'АКТИВНО',
    'LIVE NOW': 'УЖЕ В ИГРЕ',
    'EVENT LIVE': 'СОБЫТИЕ АКТИВНО',
    'EVENT ENDED': 'СОБЫТИЕ ЗАВЕРШЕНО',
    'Mirror Crew': 'Зеркальный состав',
    'Play event match': 'Играть матч события',
    'Open Dead Man’s Chest': 'Открыть Сундук мертвеца',
    "Dead Man's Chest": 'Сундук мертвеца',
    'EVENT BOX': 'ЯЩИК СОБЫТИЯ',
    'WINS TODAY': 'ПОБЕД СЕГОДНЯ',
    'COLLECTIBLES': 'КОЛЛЕКТИБЛЫ',
    'CHESTS': 'СУНДУКИ',
    'PITY': 'ГАРАНТ',
    'MAIN MECHANIC': 'ГЛАВНАЯ МЕХАНИКА',
    'DAILY LOOP': 'ЕЖЕДНЕВНЫЙ ЦИКЛ',
    'COLLECTIBLE': 'КОЛЛЕКТИБЛ',
    'PITY SYSTEM': 'СИСТЕМА ГАРАНТА',
    'Guaranteed on box 6': 'Гарантировано на 6-м сундуке',
    '4 = player choice': '4 = игрок на выбор',
    'No active Mirror cards.': 'Нет активных зеркальных карт.',
    'Premium Pass chance: 0.3% remains server-side.': 'Шанс Premium Pass 0,3% остаётся на стороне сервера.',

    'Trades': 'Обмены',

    'Trade': 'Обмен',
    'Trade unavailable.': 'Обмен недоступен.',
    'Cancel offer': 'Отменить предложение',
    'From': 'От',
    'Creator gives': 'Автор предложения отдаёт',
    'Creator wants': 'Автор предложения хочет',
    'No cards': 'Нет карт',
    'No requested assets': 'Ничего не запрошено',
    'Could not load trade options': 'Не удалось загрузить варианты обмена',
    'Create trade': 'Создать обмен',
    'All assets are validated server-side': 'Все предметы проверяются сервером',
    'Target player': 'Получатель',
    'Public market': 'Публичный рынок',
    'Want cards': 'Хочу карты',
    'Want Coins': 'Хочу монеты',
    'You want': 'Ты хочешь',
    'Coins amount': 'Количество монет',
    'Publish trade': 'Опубликовать обмен',
    'SELECTED': 'ВЫБРАНО',
    'SELECT': 'ВЫБРАТЬ',
    'No tradeable cards.': 'Нет карт, доступных для обмена.',
    'Installed X-Factors stay attached to a traded card. Standalone X-Factor trade is not exposed here because the current production trade service has no standalone X-Factor offer storage.':
      'Установленные X-Факторы остаются привязаны к карте при обмене. Отдельный обмен X-Факторов здесь не показывается, потому что текущий production-сервис обменов не хранит отдельные предложения X-Факторов.',
    'Incoming': 'Входящие',
    'Outgoing': 'Исходящие',
    'Market': 'Рынок',
    'Nothing here yet.': 'Здесь пока пусто.',
    'Create trade': 'Создать обмен',
    'New trade': 'Новый обмен',
    'Review trade': 'Проверить обмен',
    'Review offer': 'Проверить предложение',
    'Trade completed': 'Обмен завершён',
    'Trade accepted': 'Обмен принят',
    'Trade declined': 'Обмен отклонён',
    'Accept trade': 'Принять обмен',
    'Accept this trade?': 'Принять этот обмен?',
    'Confirm trade': 'Подтвердить обмен',
    'Decline': 'Отклонить',
    'Cancel': 'Отменить',
    'You give': 'Ты отдаёшь',
    'YOU GIVE': 'ТЫ ОТДАЁШЬ',
    'You get': 'Ты получаешь',
    'YOU GET': 'ТЫ ПОЛУЧАЕШЬ',
    'Choose what you get': 'Выбрать, что получить',
    'Player nickname': 'Никнейм игрока',
    'Enter a player nickname': 'Введи никнейм игрока',
    'Trade offer created': 'Предложение обмена создано',

    'My clan': 'Мой клан',
    'Top clans': 'Лучшие кланы',
    'Browse live clans': 'Посмотреть активные кланы',
    'No clans found.': 'Кланы не найдены.',
    'Creator panel': 'Панель автора',
    'Creator program': 'Программа авторов',
    'Creator panel not active': 'Панель автора не активна',
    'Subscribers': 'Подписчики',
    'Distributed': 'Распределено',
    'Bank value': 'Стоимость банка',

    'How to play': 'Как играть',
    'Build your six.': 'Собери свою шестёрку.',
    'Make each card yours.': 'Настрой каждую карту под себя.',
    'Keep playing. Keep progressing.': 'Играй дальше. Развивайся дальше.',
    'Write a HEROES story.': 'Напиши историю HEROES.',
    'Survive Cursed Mirror.': 'Переживи «Проклятое зеркало».',
    'Discover your collection.': 'Развивай свою коллекцию.',

    'Notifications': 'Уведомления',
    'A trade is waiting': 'Тебя ждёт обмен',
    'Your daily reward': 'Твоя ежедневная награда',
    'Collected today': 'Сегодня получено',
    'Settings': 'Настройки',
    'EXPERIENCE': 'ИНТЕРФЕЙС',
    'ABOUT': 'О ПРИЛОЖЕНИИ',
    'Reduced motion': 'Уменьшить анимации',
    'Keep transitions still and simple.': 'Сделать переходы проще и спокойнее.',
    'Sound effects': 'Звуковые эффекты',
    'Box reveal sounds.': 'Звуки открытия ящиков.',
    'Haptic feedback': 'Виброотклик',
    'On supported devices.': 'На поддерживаемых устройствах.',
    'Replay intro': 'Повторить заставку',

    'Something went wrong.': 'Что-то пошло не так.',
    'Try again': 'Повторить',
    'Loading…': 'Загрузка…',
    'Loading...': 'Загрузка...',
    'Page not found': 'Страница не найдена',
    'Back home': 'На главную',
    'Card not found in your account.': 'Карта не найдена в твоём аккаунте.',
    'Hero not found.': 'Герой не найден.',
    'Reward information unavailable.': 'Информация о награде недоступна.',

    'Coins': 'Монеты',
    'Rank Coins': 'Ранговые монеты',
    'Collectibles': 'Коллектиблы',
    'tracked': 'отслеживается',
    'cards': 'карт',
    'matches': 'матчей',
    'members': 'участников',
    'wins': 'побед',
    'incoming': 'входящих',
    'daily': 'ежедневных',
    'seasonal': 'сезонных',

    'FWD': 'НАП',
    'DEF': 'ЗАЩ',
    'GK': 'ВР'
  }));

  const longExact = new Map(Object.entries({
    'Open a legend at 94 OVR. Relive six career chapters in normal matches. Finish the book and evolve the same card to 100 OVR.':
      'Открой легенду с 94 OVR. Пройди шесть глав карьеры в обычных матчах. Заверши книгу и улучши эту же карту до 100 OVR.',
    'Open the career path for 100,000 Coins. The backend grants the HEROES 94 OVR card and opens Chapter I.':
      'Открой карьерную историю за 100 000 монет. Сервер выдаст карту HEROES 94 OVR и откроет главу I.',
    'Progress is tracked in normal matches with this HEROES card in the lineup.':
      'Прогресс засчитывается в обычных матчах, когда эта карта HEROES находится в составе.',
    'You receive the HEROES 94 OVR card immediately and unlock Chapter I.':
      'Ты сразу получишь карту HEROES 94 OVR и откроешь главу I.',
    'Your original HEROES 94 OVR will evolve into the 100 OVR version. You will not keep both cards.':
      'Твоя исходная карта HEROES 94 OVR улучшится до версии 100 OVR. Обе карты одновременно не останутся.',
    'The same HEROES card has evolved to 100 OVR.':
      'Эта же карта HEROES была улучшена до 100 OVR.',
    'Ghost ships, cursed fog, mirror copies and a six-box pity chase.':
      'Корабли-призраки, проклятый туман, зеркальные копии и гарант на шестом сундуке.',
    'After every event win, mirror 1 opponent card as a temporary copy: +1 OVR, event-only, 3 matches, max 3 active copies.':
      'После каждой победы в событии можно зеркалить 1 карту соперника как временную копию: +1 OVR, только в событии, на 3 матча, максимум 3 активные копии.',
    "Complete the daily 6-win track to receive a Dead Man's Chest. Daily progress resets on the event schedule while the event is active.":
      'Закрой ежедневную шкалу из 6 побед и получи Сундук мертвеца. Пока событие активно, прогресс сбрасывается по ежедневному расписанию.',
    'Collect event Collectibles (aka collectballs): 3% from matches before 6 / 6, 10% from the box, exchange 4 for 101 OVR Joe Sakic or Henrik Lundqvist.':
      'Собирай коллектиблы события: 3% шанс после матчей до заполнения 6/6 и 10% из сундука. Обменивай 4 штуки на Joe Sakic 101 OVR или Henrik Lundqvist 101 OVR.',
    'Event card may drop earlier, but if none dropped yet, the 6th Dead Man\'s Chest guarantees an event card and resets pity.':
      'Карта события может выпасть раньше, но если этого не произошло, 6-й Сундук мертвеца гарантирует карту события и сбрасывает счётчик гаранта.',
    'The event is available until September 30 at 23:59 Moscow time.':
      'Событие доступно до 30 сентября, 23:59 по московскому времени.',
    'Cursed Mirror runs from September 23, 00:00 through September 30, 23:59 Moscow time.':
      '«Проклятое зеркало» проходит с 23 сентября 00:00 до 30 сентября 23:59 по московскому времени.',
    'Free rewards are available to everyone. Premium costs 400 Energy. Firescore is guaranteed at Premium Level 1. The only Fireside Box in the Pass is at Level 30 together with Cole Caufield 100 OVR. Fireside Collectibles from the season can be used to craft every Fireside player except Caufield.':
      'Бесплатные награды доступны всем. Premium стоит 400 Energy. Firescore гарантирован на 1-м уровне Premium. Единственный Fireside Box в пропуске находится на 30-м уровне вместе с Cole Caufield 100 OVR. Коллектиблы Fireside можно использовать для крафта всех игроков Fireside, кроме Caufield.',
    'Free and Premium rewards are claimed only on the backend. Premium costs exactly 400 Energy.':
      'Бесплатные и Premium-награды выдаются только сервером. Premium стоит ровно 400 Energy.',
    'After the first opening, the normal Fireside Box odds apply. Cole Caufield is not in the box.':
      'После первого открытия действуют обычные шансы Fireside Box. Cole Caufield в этом ящике не выпадает.',
    'Cole Caufield is excluded from the box and remains the Level 30 Premium Pass player reward.':
      'Cole Caufield исключён из ящика и остаётся наградой игрока на 30-м уровне Premium Pass.',
    'Every craft consumes one permanent card rated exactly 2 OVR below the target and the listed number of Fireside Collectibles. Cole Caufield 100 is excluded and remains Premium Pass exclusive.':
      'Каждый крафт расходует одну постоянную карту ровно на 2 OVR ниже целевой и указанное количество коллектиблов Fireside. Cole Caufield 100 исключён и остаётся эксклюзивом Premium Pass.',
    'Energy is never credited by this button. Contact @teyld; after payment an administrator credits Energy through the existing admin wallet panel.':
      'Эта кнопка никогда не начисляет Energy автоматически. Напиши @teyld; после оплаты администратор начислит Energy через существующую админ-панель кошелька.',
    'До подключения платёжного провайдера оплата оформляется через @teyld. После подтверждения оплаты Energy начисляется администратором. Самостоятельного бесплатного начисления нет.':
      'До подключения платёжного провайдера оплата оформляется через @teyld. После подтверждения оплаты Energy начисляется администратором. Самостоятельного бесплатного начисления нет.',
    'Three forwards, two defenders, one goalie. Tap a card on the Team screen to inspect it; choose Edit lineup to make a change.':
      'Три нападающих, два защитника и один вратарь. Нажми на карту на экране состава, чтобы посмотреть её; выбери «Изменить состав», чтобы внести изменения.',
    'Install up to three X-Factors on a card. Applying an ability uses one inventory item. Removing or replacing it destroys the installed ability.':
      'Устанавливай до трёх X-Факторов на карту. Установка способности расходует один предмет из инвентаря. Снятие или замена уничтожает установленную способность.',
    'Normal matches earn Mastery XP: 50 for a win, 10 for a loss. Progress belongs to the player across card copies.':
      'Обычные матчи дают опыт мастерства: +50 за победу и +10 за поражение. Прогресс принадлежит игроку и общий для всех копий его карт.',
    'Open a hero for 100,000 Coins, put that exact 94 OVR card in your lineup, and complete the six career chapters in normal matches. Claiming the final reward evolves the same card to 100 OVR.':
      'Открой героя за 100 000 монет, поставь именно эту карту 94 OVR в состав и пройди шесть глав карьеры в обычных матчах. Финальная награда улучшит эту же карту до 100 OVR.',
    "Win event matches, mirror one opponent card at +1 OVR for 3 matches, fill a 6 / 6 daily win track, open a Dead Man's Chest, and collect event Collectibles for a choice of 101 OVR Sakic or Lundqvist.":
      'Побеждай в матчах события, зеркаль одну карту соперника с +1 OVR на 3 матча, заполняй ежедневную шкалу 6/6, открывай Сундук мертвеца и собирай коллектиблы для выбора Sakic 101 OVR или Lundqvist 101 OVR.',
    'Open boxes, collect cards, and inspect a trade before you accept. Installed X-Factors travel with the card.':
      'Открывай ящики, собирай карты и проверяй обмен перед подтверждением. Установленные X-Факторы передаются вместе с картой.',
    'Your account is not currently marked as an official creator. Applications and admin approval remain in the existing backend.':
      'Твой аккаунт сейчас не отмечен как официальный автор. Заявки и одобрение администратора остаются в существующей серверной системе.'
  }));

  const patterns = [
    [/^Level (\d+) \/ 30$/i, 'Уровень $1 / 30'],
    [/^Level (\d+)$/i, 'Уровень $1'],
    [/^Streak (\d+)$/i, 'Серия: $1'],
    [/^Day (\d+)$/i, 'День $1'],
    [/^DAY (\d+)$/i, 'ДЕНЬ $1'],
    [/^PART (\d+)$/i, 'ЧАСТЬ $1'],
    [/^PART (\d+) · (.+)$/i, 'ЧАСТЬ $1 · $2'],
    [/^CHAPTER (\d+)\/6$/i, 'ГЛАВА $1/6'],
    [/^CHAPTER (.+)$/i, 'ГЛАВА $1'],
    [/^(\d+) cards$/i, '$1 карт'],
    [/^(\d+) matches$/i, '$1 матчей'],
    [/^(\d+) members$/i, '$1 участников'],
    [/^(\d+) wins$/i, '$1 побед'],
    [/^(\d+) incoming$/i, '$1 входящих'],
    [/^(\d+) tracked$/i, '$1 отслеживается'],
    [/^Owned ×(\d+)$/i, 'В наличии ×$1'],
    [/^Owned: ×(\d+)$/i, 'В наличии: ×$1'],
    [/^Requires (\d+) OVR card$/i, 'Нужна карта $1 OVR'],
    [/^(\d+) material cards$/i, '$1 карт-материалов'],
    [/^(\d+) Collectibles$/i, '$1 коллектиблов'],
    [/^No new offers$/i, 'Новых предложений нет'],
    [/^Member · (.+)$/i, 'Участник · $1'],
    [/^Your clan: (.+)$/i, 'Твой клан: $1'],
    [/^vs\. (.+)$/i, 'против $1'],

    [/^From (.+)$/i, 'От: $1'],
    [/^(\d+) matches left$/i, 'осталось матчей: $1'],
    [/^Next in (\d+)h$/i, 'Следующая через $1 ч'],
    [/^Already claimed today · next in (\d+)h$/i, 'Сегодня уже получено · следующая через $1 ч'],
    [/^(\d+)\/(\d+) daily · (\d+)\/(\d+) seasonal$/i, '$1/$2 ежедневных · $3/$4 сезонных'],
    [/^(\d+) cards · (.+)$/i, '$1 карт · $2'],
    [/^(\d+) cards \+ (\d+) cosmetics · wants (.+)$/i, '$1 карт + $2 косметики · хочет $3'],
    [/^(\d+) cards · wants (.+)$/i, '$1 карт · хочет $2'],
    [/^(\d+) RP$/i, '$1 RP'],
    [/^Lineup: (.+)$/i, 'Слот состава: $1'],
    [/^Slot (\d+)$/i, 'Слот $1'],
    [/^Installed · Slot (\d+)$/i, 'Установлен · слот $1'],
    [/^Press number (\d+) to start the match$/i, 'Нажми число $1, чтобы начать матч'],
    [/^Anti-autoclick protection\. This check is valid for (\d+) seconds\.$/i, 'Защита от автокликеров. Проверка действует $1 секунд.'],
    [/^Level (\d+) \/ (\d+)$/i, 'Уровень $1 / $2']
  ];

  const attrs = ['placeholder', 'aria-label', 'title'];

  function translateCore(core) {
    if (!core || language !== 'ru') return core;
    if (longExact.has(core)) return longExact.get(core);
    if (exact.has(core)) return exact.get(core);

    for (const [re, replacement] of patterns) {
      if (re.test(core)) return core.replace(re, replacement);
    }

    let out = core;
    const inline = [
      [/\bRank Coins\b/g, 'Ранговые монеты'],
      [/\bCoins\b/g, 'монет'],
      [/\bCollectibles\b/g, 'коллектиблов'],
      [/\bmaterial cards\b/g, 'карт-материалов'],
      [/\bcards\b/g, 'карт'],
      [/\bcosmetics\b/g, 'косметики'],
      [/\bmatches\b/g, 'матчей'],
      [/\bmembers\b/g, 'участников'],
      [/\bwins\b/g, 'побед'],
      [/\bincoming\b/g, 'входящих'],
      [/\bdaily\b/g, 'ежедневных'],
      [/\bseasonal\b/g, 'сезонных'],
      [/\bwants\b/g, 'хочет'],
      [/\bFWD\b/g, 'НАП'],
      [/\bDEF\b/g, 'ЗАЩ'],
      [/\bGK\b/g, 'ВР'],
      [/\bOPEN\b/g, 'ОТКРЫТО'],
      [/\bCANCELLED\b/g, 'ОТМЕНЕНО'],
      [/\bDECLINED\b/g, 'ОТКЛОНЕНО'],
      [/\bACCEPTED\b/g, 'ПРИНЯТО'],
      [/\bWIN\b/g, 'ПОБЕДА'],
      [/\bLOSS\b/g, 'ПОРАЖЕНИЕ']
    ];
    for (const [re, replacement] of inline) out = out.replace(re, replacement);
    return out;
  }

  function translateText(text) {
    if (language !== 'ru' || !text || !text.trim()) return text;
    const leading = text.match(/^\s*/)?.[0] || '';
    const trailing = text.match(/\s*$/)?.[0] || '';
    const core = text.slice(leading.length, text.length - trailing.length || undefined);
    return leading + translateCore(core) + trailing;
  }

  function shouldSkip(node) {
    const parent = node.parentElement;
    return !parent || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'PRE'].includes(parent.tagName);
  }

  function localizeNode(root) {
    if (language !== 'ru' || !root) return;

    if (root.nodeType === Node.TEXT_NODE) {
      if (!shouldSkip(root)) {
        const translated = translateText(root.nodeValue);
        if (translated !== root.nodeValue) root.nodeValue = translated;
      }
      return;
    }

    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;

    if (root.nodeType === Node.ELEMENT_NODE) {
      for (const attr of attrs) {
        if (root.hasAttribute(attr)) {
          const value = root.getAttribute(attr);
          const translated = translateCore(value);
          if (translated !== value) root.setAttribute(attr, translated);
        }
      }
    }

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (shouldSkip(node)) continue;
      const translated = translateText(node.nodeValue);
      if (translated !== node.nodeValue) node.nodeValue = translated;
    }

    if (root.querySelectorAll) {
      root.querySelectorAll('[placeholder],[aria-label],[title]').forEach(el => {
        for (const attr of attrs) {
          if (!el.hasAttribute(attr)) continue;
          const value = el.getAttribute(attr);
          const translated = translateCore(value);
          if (translated !== value) el.setAttribute(attr, translated);
        }
      });
    }
  }

  function settingsLanguageBlock() {
    const ruActive = language === 'ru';
    return `
      <div class="list nexcore-language-settings">
        <div class="list-title">${ruActive ? 'ЯЗЫК' : 'LANGUAGE'}</div>
        <div class="list-row" style="align-items:flex-start">
          <span class="row-text">
            <strong>${ruActive ? 'Язык интерфейса' : 'Interface language'}</strong>
            <small>${ruActive ? 'Русский используется по умолчанию. Язык можно изменить в любой момент.' : 'Russian is the default. You can change the language at any time.'}</small>
          </span>
          <span style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">
            <button class="chip ${ruActive ? 'active' : ''}" data-nexcore-language="ru">Русский</button>
            <button class="chip ${!ruActive ? 'active' : ''}" data-nexcore-language="en">English</button>
          </span>
        </div>
      </div>`;
  }

  function ensureLanguageSetting() {
    const route = (location.hash || '#home').slice(1).split('/')[0];
    if (route !== 'settings') return;
    const main = document.querySelector('main');
    if (!main || main.querySelector('.nexcore-language-settings')) return;

    const firstList = main.querySelector('.list');
    if (firstList) firstList.insertAdjacentHTML('beforebegin', settingsLanguageBlock());
    else main.insertAdjacentHTML('beforeend', settingsLanguageBlock());
  }

  let scheduled = false;
  function apply() {
    scheduled = false;
    document.documentElement.lang = language;
    if (language === 'ru') {
      localizeNode(document.body);
      // MutationObserver watches characterData/childList. Assigning document.title
      // on every pass, even to the same string, can create an endless microtask
      // feedback loop that starves app.js and leaves Telegram on a black screen.
      const translatedTitle = translateCore(document.title);
      if (translatedTitle !== document.title) document.title = translatedTitle;
      const meta = document.querySelector('meta[name="description"]');
      if (meta) {
        const translatedDescription = translateCore(meta.content);
        if (translatedDescription !== meta.content) meta.content = translatedDescription;
      }
    }
    ensureLanguageSetting();
  }

  function scheduleApply() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(apply);
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-nexcore-language]');
    if (!button) return;
    const next = button.getAttribute('data-nexcore-language');
    if (!supported.has(next) || next === language) return;
    localStorage.setItem(STORAGE_KEY, next);
    location.reload();
  });

  const observer = new MutationObserver(scheduleApply);
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: attrs
  });

  window.addEventListener('hashchange', scheduleApply);
  apply();
})();
