// Parent applications may supply their gateway token for this tab. No second login system.
(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin) {
      const token = sessionStorage.getItem('fiscycleGatewayToken');
      if (token) { const headers = new Headers(options.headers); headers.set('Authorization', `Bearer ${token}`); options = {...options, headers}; }
    }
    return nativeFetch(input, options);
  };
})();
