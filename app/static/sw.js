// Service worker: keeps the app shell available when the Pi can't be reached.
// Network first, so a new deploy shows up on the next load; the cache is only a fallback.
// /api/ requests are never cached: the scanner must always show live data.
'use strict';

const CACHE = 'apt-obd-v13'; // bump to drop every cached copy on the next visit
const SHELL = [
  '/',
  '/setup',
  '/static/fonts.css',
  '/static/scantool.css',
  '/static/scantool.js',
  '/static/setup.css',
  '/static/setup.js',
  '/static/fonts/chakra-petch-500-latin.woff2',
  '/static/fonts/chakra-petch-600-latin.woff2',
  '/static/fonts/vt323-400-latin.woff2',
  '/static/icons/apple-touch-icon.png',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  event.respondWith(
    fetch(event.request, { cache: 'no-cache' }) // always check with the Pi, never the HTTP cache
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});

// Notifications from the Pi (see app/push.py). iOS requires every push to show a notification.
self.addEventListener('push', event => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(self.registration.showNotification(data.title || 'APT-OBD', {
    body: data.body || '',
    tag: data.tag,
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    data: { url: data.url || '/' },
  }));
});

// Tapping a notification opens the scanner, reusing an open window if there is one.
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windows => {
      const open = windows.find(w => new URL(w.url).origin === location.origin);
      return open ? open.focus().then(w => w.navigate(url)) : self.clients.openWindow(url);
    }),
  );
});
