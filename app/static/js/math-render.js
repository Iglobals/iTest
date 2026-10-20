/*
 * Shared math helpers for every screen that shows exam questions/options
 * (builder, exam-taking, results, grading). Requires KaTeX to be loaded first.
 *
 * - iTestMath.toLatex(src): turns everyday math typing ("3/4", "(x-3)/(x-4)",
 *   "sqrt(x+1)", "int_0^1 x^2 dx", "d/dx(x^2)", "diff(x^2)", "x<=3", "2*pi")
 *   into LaTeX. Input that already looks like LaTeX (has \ { or }) is
 *   returned untouched, so re-running it on a stored value is a no-op.
 * - iTestMath.renderAll(root): re-renders every Quill formula
 *   (<span class="ql-formula" data-value="...">) with KaTeX. Runs on page load.
 */
(function () {
    const GREEK = ['alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota',
        'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma', 'tau', 'upsilon', 'phi',
        'chi', 'psi', 'omega', 'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi', 'Sigma',
        'Phi', 'Psi', 'Omega'];
    const FUNCS = ['sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'arcsin', 'arccos', 'arctan',
        'sinh', 'cosh', 'tanh', 'log', 'ln', 'exp', 'min', 'max', 'det'];
    const WORDS = {
        int: '\\int ', integral: '\\int ', iint: '\\iint ', oint: '\\oint ',
        sum: '\\sum ', prod: '\\prod ', lim: '\\lim ',
        inf: '\\infty ', infinity: '\\infty ', partial: '\\partial ',
        deg: '^{\\circ}', times: '\\times ', div: '\\div ',
    };
    // Longest first so "<=" wins over "<", "+/-" over "+", etc.
    const OPS = [
        ['+/-', '\\pm '], ['+-', '\\pm '], ['-+', '\\mp '], ['<=>', '\\iff '],
        ['<=', '\\le '], ['>=', '\\ge '], ['!=', '\\ne '], ['=/=', '\\ne '],
        ['~=', '\\approx '], ['->', '\\to '], ['=>', '\\Rightarrow '],
        ['*', '\\times '], ['×', '\\times '], ['÷', '\\div '],
        ['≤', '\\le '], ['≥', '\\ge '], ['≠', '\\ne '],
        ['±', '\\pm '], ['π', '\\pi '], ['∞', '\\infty '],
        ['°', '^{\\circ}'], ['%', '\\%'],
    ];

    function toLatex(src) {
        src = String(src == null ? '' : src).trim();
        if (!src || /[\\{}]/.test(src)) return src;
        const s = src.replace(/√/g, 'sqrt');
        let i = 0;

        const skipSpaces = () => { while (i < s.length && /\s/.test(s[i])) i++; };

        function word(w) {
            if (GREEK.includes(w)) return '\\' + w + ' ';
            if (FUNCS.includes(w)) return '\\' + w + ' ';
            if (WORDS[w]) return WORDS[w];
            return w;
        }

        // Grab the raw text of a (...) group starting at s[i] === '('.
        function rawParen() {
            let depth = 0, start = i;
            for (; i < s.length; i++) {
                if (s[i] === '(') depth++;
                else if (s[i] === ')' && --depth === 0) { i++; return s.slice(start + 1, i - 1); }
            }
            return s.slice(start + 1);
        }

        function splitTopComma(str) {
            let depth = 0;
            for (let k = str.length - 1; k >= 0; k--) {
                const c = str[k];
                if (c === ')') depth++;
                else if (c === '(') depth--;
                else if (c === ',' && depth === 0) return [str.slice(0, k), str.slice(k + 1)];
            }
            return [str, null];
        }

        // "sin(x)", "f(x)", "2(x+1)" - a group written directly after a
        // word/number belongs to it, so "sin(x)/x" puts sin(x) on top.
        function withCall(tex) {
            if (s[i] !== '(') return { tex, inner: tex };
            const group = parseAtom();
            const t = tex.replace(/ $/, '') + group.tex;
            return { tex: t, inner: t };
        }

        // An "atom" is one operand: number, word, (group), sqrt(...), etc.
        // `inner` is the content without visible brackets, used when the
        // atom becomes a fraction part / exponent so "(x-3)/(x-4)" loses
        // its parentheses inside \frac.
        function parseAtom(noCoef) {
            skipSpaces();
            const c = s[i];
            if (c === undefined) return { tex: '', inner: '' };
            if (c === '-' || c === '+') {
                i++;
                const a = parseAtom(noCoef);
                return { tex: c + a.tex, inner: c + a.inner };
            }
            if (c === '(' || c === '[') {
                const close = c === '(' ? ')' : ']';
                i++;
                const inner = parseExpr(close);
                if (s[i] === close) i++;
                const tex = c === '(' ? `\\left(${inner}\\right)` : `\\left[${inner}\\right]`;
                return { tex, inner };
            }
            let m = /^\d+(?:\.\d+)?/.exec(s.slice(i));
            if (m) {
                i += m[0].length;
                // "2x", "3pi" - keep coefficient and variable as one operand
                const w = /^[a-zA-Z]+/.exec(s.slice(i));
                let tex = m[0];
                if (w && !noCoef && w[0] !== 'd') { i += w[0].length; tex += word(w[0]); }
                return noCoef ? { tex, inner: tex } : withCall(tex);
            }
            m = /^[a-zA-Z]+/.exec(s.slice(i));
            if (m) {
                const w = m[0];
                i += w.length;
                if (w === 'sqrt' || w === 'cbrt' || w === 'root') {
                    skipSpaces();
                    const a = parseAtom();
                    const tex = w === 'cbrt' ? `\\sqrt[3]{${a.inner}}` : `\\sqrt{${a.inner}}`;
                    return { tex, inner: tex };
                }
                if ((w === 'diff' || w === 'deriv' || w === 'derivative') && (skipSpaces(), s[i] === '(')) {
                    const [expr, v] = splitTopComma(rawParen());
                    const tex = `\\frac{d}{d${(v || 'x').trim()}}\\left(${toLatex(expr)}\\right)`;
                    return { tex, inner: tex };
                }
                if (w === 'abs' && (skipSpaces(), s[i] === '(')) {
                    i++;
                    const inner = parseExpr(')');
                    if (s[i] === ')') i++;
                    const tex = `\\left|${inner}\\right|`;
                    return { tex, inner: tex };
                }
                return withCall(word(w));
            }
            i++;
            return { tex: c, inner: c };
        }

        function parseExpr(closer) {
            const out = []; // pieces: { tex, inner, atom, space }
            const popOperand = () => {
                while (out.length && out[out.length - 1].space) out.pop();
                return out.length && out[out.length - 1].atom ? out.pop() : { tex: '', inner: '' };
            };
            while (i < s.length) {
                const c = s[i];
                if (closer && c === closer) break;
                if (/\s/.test(c)) { i++; out.push({ tex: ' ', space: true }); continue; }

                const op = OPS.find(([k]) => s.startsWith(k, i));
                if (op) { i += op[0].length; out.push({ tex: op[1], atom: op[1].startsWith('^') }); continue; }

                if (c === '/') {
                    i++;
                    const num = popOperand();
                    const den = parseAtom();
                    out.push({ tex: `\\frac{${num.inner}}{${den.inner}}`, inner: `\\frac{${num.inner}}{${den.inner}}`, atom: true });
                    continue;
                }
                if (c === '^' || c === '_') {
                    i++;
                    const base = popOperand();
                    const a = parseAtom(true); // "x^2y" -> x^{2}y, not x^{2y}
                    const tex = `${base.tex || '{}'}${c}{${a.inner}}`;
                    out.push({ tex, inner: tex, atom: true });
                    continue;
                }
                // Binary minus/plus and relations are not operands, so
                // "x - 3/4" keeps the minus outside the fraction.
                if ('+-=<>,;:'.includes(c)) { i++; out.push({ tex: c }); continue; }
                if (c === ')' || c === ']') { i++; out.push({ tex: c }); continue; } // stray closer
                const a = parseAtom();
                a.atom = true;
                out.push(a);
            }
            return out.map(p => p.tex).join('').replace(/\s+/g, ' ').trim();
        }

        try {
            return parseExpr(null);
        } catch (e) {
            return src;
        }
    }

    function renderAll(root) {
        if (typeof katex === 'undefined') return;
        (root || document).querySelectorAll('.ql-formula[data-value]').forEach(el => {
            // Skip formulas living inside a live Quill editor - Quill owns those.
            if (el.closest('.ql-editor')) return;
            try {
                // toLatex also upgrades formulas saved before the converter
                // existed (data-value "3/4" instead of "\frac{3}{4}").
                katex.render(toLatex(el.getAttribute('data-value')), el, { throwOnError: false, errorColor: '#ef4444' });
            } catch (e) { /* leave whatever was there */ }
        });
    }

    // Wide fractions/integrals must never push a phone layout sideways.
    const style = document.createElement('style');
    style.textContent = '.ql-formula{display:inline-block;max-width:100%;overflow-x:auto;overflow-y:hidden;vertical-align:middle;}' +
        '.ql-formula .katex{font-size:1.1em;}';
    document.head.appendChild(style);

    window.iTestMath = { toLatex, renderAll };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => renderAll());
    } else {
        renderAll();
    }
})();
