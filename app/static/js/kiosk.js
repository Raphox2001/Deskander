const POLL_INTERVAL_MS = 10000;
const WEEKDAY_LABELS_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const WEEKDAY_LABELS_FULL = [
  "Montag",
  "Dienstag",
  "Mittwoch",
  "Donnerstag",
  "Freitag",
  "Samstag",
  "Sonntag",
];
const TIMELINE_DEFAULT_START_HOUR = 7;
const TIMELINE_DEFAULT_END_HOUR = 23;
const TIMELINE_LANE_HEIGHT_EM = 2.1;

function formatTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function formatTimeFromDate(date) {
  return date.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

function formatTimeRange(event) {
  if (event.all_day) {
    return "Ganztägig";
  }
  return `${formatTime(event.start)}–${formatTime(event.end)}`;
}

function hourFraction(date) {
  return date.getHours() + date.getMinutes() / 60 + date.getSeconds() / 3600;
}

function updateClock() {
  const now = new Date();
  const dateEl = document.getElementById("current-date");
  const timeEl = document.getElementById("current-time");

  dateEl.textContent = now.toLocaleDateString("de-DE", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const seconds = String(now.getSeconds()).padStart(2, "0");
  timeEl.innerHTML = `${hours}:${minutes}<span class="seconds">${seconds}</span>`;
}

function todayIsoDate() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function splitTodaysEvents(agenda, today) {
  const todays = (agenda || []).filter(
    (e) => e.start.slice(0, 10) <= today && e.end.slice(0, 10) >= today
  );
  return {
    allDay: todays.filter((e) => e.all_day),
    timed: todays.filter((e) => !e.all_day),
  };
}

function renderAllDay(allDayEvents) {
  const row = document.getElementById("allday-row");
  row.innerHTML = "";
  row.style.display = allDayEvents.length ? "flex" : "none";

  for (const event of allDayEvents) {
    const chip = document.createElement("span");
    chip.className = "allday-chip";
    chip.style.background = event.color || "#6fa8dc";
    chip.textContent = event.title;
    row.appendChild(chip);
  }
}

function assignTimelineLanes(events) {
  const laneEndTimes = [];
  const withLanes = [];
  for (const event of events) {
    let laneIndex = laneEndTimes.findIndex((endMs) => endMs <= event.startMs);
    if (laneIndex === -1) {
      laneIndex = laneEndTimes.length;
      laneEndTimes.push(event.endMs);
    } else {
      laneEndTimes[laneIndex] = event.endMs;
    }
    withLanes.push({ ...event, lane: laneIndex });
  }
  return { events: withLanes, laneCount: Math.max(laneEndTimes.length, 1) };
}

let currentTimelineRange = null;

function updateNowLine() {
  const lineEl = document.getElementById("timeline-now-line");
  if (!lineEl || !currentTimelineRange) return;
  const { startHour, endHour } = currentTimelineRange;
  const frac = hourFraction(new Date());
  if (frac < startHour || frac > endHour) {
    lineEl.style.display = "none";
    return;
  }
  const pct = ((frac - startHour) / (endHour - startHour)) * 100;
  lineEl.style.display = "block";
  lineEl.style.left = `${pct}%`;
}

function renderTimeline(timedEvents) {
  const hoursEl = document.getElementById("timeline-hours");
  const trackEl = document.getElementById("timeline-track");
  const emptyEl = document.getElementById("timeline-empty");
  hoursEl.innerHTML = "";
  trackEl.innerHTML = "";

  if (!timedEvents || timedEvents.length === 0) {
    hoursEl.style.display = "none";
    trackEl.style.display = "none";
    emptyEl.style.display = "block";
    emptyEl.textContent = "Keine Termine heute";
    currentTimelineRange = null;
    return;
  }
  hoursEl.style.display = "block";
  trackEl.style.display = "block";
  emptyEl.style.display = "none";

  const dayStart = new Date();
  dayStart.setHours(0, 0, 0, 0);
  const dayEnd = new Date(dayStart);
  dayEnd.setDate(dayEnd.getDate() + 1);

  // Clip multi-day events to today's slice, since the timeline only covers today.
  const prepared = timedEvents
    .map((event) => {
      const start = new Date(event.start);
      const end = new Date(event.end);
      const startDate = start < dayStart ? dayStart : start;
      const endDate = end > dayEnd ? dayEnd : end;
      return { ...event, startDate, endDate, startMs: startDate.getTime(), endMs: endDate.getTime() };
    })
    .sort((a, b) => a.startMs - b.startMs);

  // Auto-expand the range if an event starts earlier or ends later than the default window.
  let rangeStartHour = TIMELINE_DEFAULT_START_HOUR;
  let rangeEndHour = TIMELINE_DEFAULT_END_HOUR;
  for (const event of prepared) {
    rangeStartHour = Math.min(rangeStartHour, Math.floor(hourFraction(event.startDate)));
    rangeEndHour = Math.max(rangeEndHour, Math.ceil(hourFraction(event.endDate)));
  }
  const rangeHours = Math.max(rangeEndHour - rangeStartHour, 1);
  const hourStep = rangeHours > 16 ? 2 : 1;

  // Quarter-hour ticks (finer/dimmer), drawn first so they sit behind hour ticks.
  for (let quarter = rangeStartHour * 4; quarter <= rangeEndHour * 4; quarter += 1) {
    if (quarter % 4 === 0) continue; // full hours drawn separately below
    const pct = ((quarter / 4 - rangeStartHour) / rangeHours) * 100;
    const line = document.createElement("div");
    line.className = "timeline-quarter-line";
    line.style.left = `${pct}%`;
    trackEl.appendChild(line);
  }

  // Full-hour ticks + small hour labels above the track.
  for (let hour = rangeStartHour; hour <= rangeEndHour; hour += 1) {
    const pct = ((hour - rangeStartHour) / rangeHours) * 100;

    const line = document.createElement("div");
    line.className = "timeline-hour-line";
    line.style.left = `${pct}%`;
    trackEl.appendChild(line);

    if ((hour - rangeStartHour) % hourStep === 0) {
      const label = document.createElement("div");
      label.className = "hour-label";
      label.style.left = `${pct}%`;
      label.textContent = String(hour);
      hoursEl.appendChild(label);
    }
  }

  const { events: laned, laneCount } = assignTimelineLanes(prepared);
  trackEl.style.height = `${laneCount * TIMELINE_LANE_HEIGHT_EM}em`;

  for (const event of laned) {
    const startFrac = (hourFraction(event.startDate) - rangeStartHour) / rangeHours;
    const endFrac = (hourFraction(event.endDate) - rangeStartHour) / rangeHours;
    const left = Math.max(0, startFrac) * 100;
    const width = Math.max(0.8, (Math.min(1, endFrac) - Math.max(0, startFrac)) * 100);

    const block = document.createElement("div");
    block.className = "timeline-event";
    block.style.left = `${left}%`;
    block.style.width = `${width}%`;
    block.style.top = `${event.lane * TIMELINE_LANE_HEIGHT_EM}em`;
    block.style.height = `${TIMELINE_LANE_HEIGHT_EM - 0.2}em`;
    block.style.background = event.color || "#6fa8dc";
    block.textContent = event.title;
    block.title = `${event.title} (${formatTimeFromDate(event.startDate)}–${formatTimeFromDate(event.endDate)})`;
    trackEl.appendChild(block);
  }

  const nowLine = document.createElement("div");
  nowLine.id = "timeline-now-line";
  nowLine.className = "timeline-now-line";
  trackEl.appendChild(nowLine);

  currentTimelineRange = { startHour: rangeStartHour, endHour: rangeEndHour };
  updateNowLine();
}

function renderWeather(weather) {
  const currentEl = document.getElementById("weather-current");
  const forecastEl = document.getElementById("weather-forecast");
  currentEl.innerHTML = "";
  forecastEl.innerHTML = "";

  if (!weather || !weather.current) {
    currentEl.textContent = "Wetter nicht verfügbar";
    return;
  }

  const temp = document.createElement("span");
  temp.textContent = `${Math.round(weather.current.temperature)}°C`;

  const desc = document.createElement("span");
  desc.textContent = weather.current.description || "";
  desc.style.fontSize = "0.5em";

  const place = document.createElement("span");
  place.className = "place";
  place.textContent = weather.place_name || "";

  currentEl.appendChild(temp);
  currentEl.appendChild(desc);
  currentEl.appendChild(place);

  for (const day of weather.daily || []) {
    const dayEl = document.createElement("div");
    dayEl.className = "day";

    const label = document.createElement("div");
    label.className = "day-label";
    const d = new Date(day.date + "T00:00:00");
    label.textContent = WEEKDAY_LABELS_SHORT[(d.getDay() + 6) % 7];

    const temps = document.createElement("div");
    temps.textContent = `${Math.round(day.temperature_max)}°/${Math.round(day.temperature_min)}°`;

    dayEl.appendChild(label);
    dayEl.appendChild(temps);
    forecastEl.appendChild(dayEl);
  }
}

function collectWeekAllDayBars(week) {
  // Each all-day event appears once per day it spans in the backend payload
  // (one dict per day-in-range). Collapse those duplicates back into a
  // single bar per event, spanning from its first to its last day this week.
  const map = new Map();
  week.days.forEach((day, dayIndex) => {
    for (const event of day.events) {
      if (!event.all_day) continue;
      const key = `${event.source_id}|${event.title}|${event.start}|${event.end}`;
      const existing = map.get(key);
      if (existing) {
        existing.startIndex = Math.min(existing.startIndex, dayIndex);
        existing.endIndex = Math.max(existing.endIndex, dayIndex);
      } else {
        map.set(key, { event, startIndex: dayIndex, endIndex: dayIndex });
      }
    }
  });
  return Array.from(map.values());
}

function assignBarLanes(bars) {
  const sorted = [...bars].sort(
    (a, b) => a.startIndex - b.startIndex || b.endIndex - a.endIndex
  );
  const laneEndIndex = [];
  const withLanes = [];
  for (const bar of sorted) {
    let lane = laneEndIndex.findIndex((endIndex) => endIndex < bar.startIndex);
    if (lane === -1) {
      lane = laneEndIndex.length;
      laneEndIndex.push(bar.endIndex);
    } else {
      laneEndIndex[lane] = bar.endIndex;
    }
    withLanes.push({ ...bar, lane });
  }
  return { bars: withLanes, laneCount: laneEndIndex.length };
}

function renderCalendar(weeks, showWeekNumbers) {
  const weekdaysEl = document.getElementById("calendar-weekdays");
  const gridEl = document.getElementById("calendar-grid");

  weekdaysEl.classList.toggle("with-weeknum", !!showWeekNumbers);

  weekdaysEl.innerHTML = "";
  if (showWeekNumbers) {
    weekdaysEl.appendChild(document.createElement("div"));
  }
  for (const label of WEEKDAY_LABELS_FULL) {
    const el = document.createElement("div");
    el.textContent = label;
    weekdaysEl.appendChild(el);
  }

  gridEl.innerHTML = "";
  const today = todayIsoDate();
  const colOffset = showWeekNumbers ? 1 : 0;

  for (const week of weeks || []) {
    const { bars, laneCount } = assignBarLanes(collectWeekAllDayBars(week));

    const weekEl = document.createElement("div");
    weekEl.className = "calendar-week";
    weekEl.classList.toggle("with-weeknum", !!showWeekNumbers);
    weekEl.style.gridTemplateRows = laneCount > 0 ? `repeat(${laneCount}, auto) 1fr` : "1fr";

    if (showWeekNumbers) {
      const weekNumEl = document.createElement("div");
      weekNumEl.className = "calendar-weeknum";
      weekNumEl.textContent = `KW ${week.week_number}`;
      weekNumEl.style.gridColumn = "1";
      weekNumEl.style.gridRow = `1 / span ${laneCount + 1}`;
      weekEl.appendChild(weekNumEl);
    }

    for (const bar of bars) {
      const barEl = document.createElement("div");
      barEl.className = "allday-bar";
      barEl.style.gridColumn = `${colOffset + bar.startIndex + 1} / ${colOffset + bar.endIndex + 2}`;
      barEl.style.gridRow = `${bar.lane + 1}`;
      barEl.style.background = bar.event.color || "#6fa8dc";
      barEl.textContent = bar.event.title;
      barEl.title = bar.event.title;
      weekEl.appendChild(barEl);
    }

    week.days.forEach((day, dayIndex) => {
      const dayEl = document.createElement("div");
      dayEl.className = "calendar-day";
      if (day.date === today) {
        dayEl.classList.add("today");
      }
      dayEl.style.gridColumn = `${colOffset + dayIndex + 1}`;
      dayEl.style.gridRow = `${laneCount + 1}`;

      const number = document.createElement("div");
      number.className = "day-number";
      number.textContent = String(parseInt(day.date.slice(8, 10), 10));
      dayEl.appendChild(number);

      for (const event of day.events) {
        if (event.all_day) continue; // rendered as bars above, not per-day
        const evEl = document.createElement("div");
        evEl.className = "event timed";
        evEl.style.color = event.color || "#6fa8dc";
        evEl.textContent = `${formatTime(event.start)} ${event.title}`;
        dayEl.appendChild(evEl);
      }

      weekEl.appendChild(dayEl);
    });

    gridEl.appendChild(weekEl);
  }
}

function renderStatus(data) {
  const el = document.getElementById("status-bar");
  const calTime = data.calendar_updated_at
    ? new Date(data.calendar_updated_at).toLocaleTimeString("de-DE")
    : "-";
  const weatherTime = data.weather_updated_at
    ? new Date(data.weather_updated_at).toLocaleTimeString("de-DE")
    : "-";
  el.textContent = `Kalender aktualisiert: ${calTime} · Wetter: ${weatherTime}`;

  const adminEl = document.getElementById("admin-url");
  if (data.admin_url) {
    adminEl.textContent = `Admin: ${data.admin_url}`;
    adminEl.style.display = "";
  } else {
    adminEl.style.display = "none";
  }
}

let knownBackendBootId = null;

async function refresh() {
  try {
    const response = await fetch("/display/data", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();

    // The backend generates a fresh boot id on every process start. If it
    // changes after we've already seen one, the backend was restarted
    // (deploy/update/crash-restart) - reload so this tab picks up the new
    // HTML/CSS/JS instead of running stale code indefinitely.
    if (knownBackendBootId === null) {
      knownBackendBootId = data.backend_boot_id;
    } else if (data.backend_boot_id && data.backend_boot_id !== knownBackendBootId) {
      window.location.reload();
      return;
    }

    const { allDay, timed } = splitTodaysEvents(data.agenda, todayIsoDate());
    renderAllDay(allDay);
    renderTimeline(timed);
    renderWeather(data.weather);
    renderCalendar(data.calendar_weeks, data.show_week_numbers);
    renderStatus(data);
  } catch (err) {
    console.error("Konnte /display/data nicht laden:", err);
  }
}

updateClock();
updateNowLine();
setInterval(() => {
  updateClock();
  updateNowLine();
}, 1000);

refresh();
setInterval(refresh, POLL_INTERVAL_MS);
