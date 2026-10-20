/*
 * The server refreshes expired access tokens on its own (see
 * app/auth/decorators.py). If a call still comes back 401 with
 * login_required, the refresh token itself is gone - send the user to log in
 * instead of letting the page show a generic "unexpected error".
 */
(function () {
    if (!window.fetch || window.__iTestAuthFetch) return;
    window.__iTestAuthFetch = true;
    const nativeFetch = window.fetch.bind(window);
    let redirecting = false;

    window.fetch = function (input, init) {
        return nativeFetch(input, init).then(res => {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            const sameOrigin = !/^https?:\/\//i.test(url) || url.startsWith(location.origin);
            if (res.status === 401 && sameOrigin && !redirecting) {
                res.clone().json().then(data => {
                    if (data && data.login_required && !redirecting) {
                        redirecting = true;
                        if (typeof showToast === 'function') showToast('Your session has expired. Redirecting to login...');
                        setTimeout(() => { location.href = '/auth/login'; }, 1200);
                    }
                }).catch(() => {});
            }
            return res;
        });
    };
})();
