import { forwardRef, useRef, useLayoutEffect, useEffect, useCallback } from 'react';
import { ChevronDown } from 'lucide-react';

export const Input = forwardRef(function Input({ label, error, className = '', ...props }, ref) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-sm font-medium text-gray-700">
          {label}
          {props.required && <span className="text-red-500 ml-1 font-bold">*</span>}
        </label>
      )}
      <input
        ref={ref}
        className={`
          w-full px-3 py-2.5 text-sm text-gray-900 bg-white border rounded-lg
          placeholder-gray-400 transition-all duration-150
          focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-400
          disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed
          ${error ? 'border-error focus:ring-error' : 'border-gray-200'}
          ${className}
        `}
        {...props}
      />
      {error && <span className="text-xs text-error">{error}</span>}
    </div>
  );
});

export const Textarea = forwardRef(function Textarea({ label, error, className = '', onChange, value, ...props }, ref) {
  const innerRef = useRef(null);

  // Combina o ref interno (para medir a altura) com o ref encaminhado.
  const setRefs = useCallback((node) => {
    innerRef.current = node;
    if (typeof ref === 'function') ref(node);
    else if (ref) ref.current = node;
  }, [ref]);

  // Cresce o campo para caber todo o texto digitado (quebra a linha para baixo).
  const autoGrow = useCallback(() => {
    const el = innerRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  // Reajusta quando o valor muda externamente (carregar relatório, reset, etc.).
  // Recalcula de novo no próximo paint e após o carregamento das fontes: a
  // 1ª medição pode sair baixa demais se a fonte final ainda não tiver sido
  // aplicada nesse instante (document.fonts.status já pode dizer 'loaded'
  // antes da fonte usada aqui realmente refletir no layout — por isso
  // dependia só disso ainda cortava texto de forma intermitente ao abrir um
  // relatório salvo). requestAnimationFrame não depende desse status.
  useLayoutEffect(() => {
    autoGrow();
    const raf = requestAnimationFrame(autoGrow);
    document.fonts?.ready?.then(autoGrow);
    return () => cancelAnimationFrame(raf);
  }, [value, autoGrow]);

  // Reage a qualquer mudança real de largura do próprio campo (ex.: uma
  // tabela vizinha ainda ajustando a largura das colunas em mais de um
  // reflow) — mais robusto que contar frames, que às vezes não bastava.
  useEffect(() => {
    const el = innerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => autoGrow());
    ro.observe(el);
    return () => ro.disconnect();
  }, [autoGrow]);

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-sm font-medium text-gray-700">
          {label}
          {props.required && <span className="text-red-500 ml-1 font-bold">*</span>}
        </label>
      )}
      <textarea
        ref={setRefs}
        value={value}
        onChange={(e) => { onChange?.(e); autoGrow(); }}
        className={`
          w-full px-3 py-2.5 text-sm text-gray-900 bg-white border rounded-lg resize-none overflow-hidden
          placeholder-gray-400 transition-all duration-150
          focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-400
          disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed
          ${error ? 'border-error focus:ring-error' : 'border-gray-200'}
          ${className}
        `}
        {...props}
      />
      {error && <span className="text-xs text-error">{error}</span>}
    </div>
  );
});

export const Select = forwardRef(function Select({ label, error, children, className = '', ...props }, ref) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-sm font-medium text-gray-700">
          {label}
          {props.required && <span className="text-red-500 ml-1 font-bold">*</span>}
        </label>
      )}
      <div className="relative">
        <select
          ref={ref}
          className={`
            w-full px-3 py-2.5 text-sm text-gray-900 bg-white border rounded-lg appearance-none pr-9
            placeholder-gray-400 transition-all duration-150
            focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-400
            disabled:bg-gray-50 disabled:text-gray-400 disabled:cursor-not-allowed
            ${error ? 'border-error focus:ring-error' : 'border-gray-200'}
            ${className}
          `}
          {...props}
        >
          {children}
        </select>
        <ChevronDown size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      </div>
      {error && <span className="text-xs text-error">{error}</span>}
    </div>
  );
});
