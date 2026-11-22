// Ayudas de accesibilidad compartidas (evaluación de usabilidad, problemas 11 y 12).
import { useEffect, useRef, type FormEvent } from "react";
import { pageTitle } from "./format";

/** Título del documento por pantalla (WCAG 2.4.2). */
export function usePageTitle(screen: string | null | undefined) {
  useEffect(() => {
    document.title = pageTitle(screen);
  }, [screen]);
}

/**
 * Lleva el foco a un elemento cuando `when` pasa a true (p. ej. el botón «Confirmar» al
 * abrir una confirmación), para que el teclado y los lectores de pantalla no queden en <body>.
 */
export function useFocusWhen<T extends HTMLElement>(when: boolean) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    if (when) ref.current?.focus();
  }, [when]);
  return ref;
}

/** Enfoca el encabezado principal de la pantalla (o el contenedor) después de una navegación. */
export function focusMainHeading(root: HTMLElement | null) {
  if (!root) return;
  const heading = root.querySelector<HTMLElement>("h1, h2") ?? root;
  if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
  heading.focus({ preventScroll: true });
}

type Validable = HTMLInputElement | HTMLTextAreaElement;

/**
 * Evaluación de usabilidad, corrida 2: el mensaje de la validación nativa de un campo obligatorio
 * vacío lo pone el navegador en su idioma (en un Chromium en inglés, «Please fill out this
 * field.»). Con estas props el mensaje queda en castellano, sea cual sea el idioma del navegador.
 */
export const requiredFieldProps = {
  required: true,
  onInvalid: (e: FormEvent<Validable>) => {
    if (e.currentTarget.validity.valueMissing) e.currentTarget.setCustomValidity("Completá este campo.");
  },
  onInput: (e: FormEvent<Validable>) => e.currentTarget.setCustomValidity(""),
};
