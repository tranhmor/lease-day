import zh from './zh.json';
import en from './en.json';
import type { Lang } from '@/types/viz';

export type Dict = typeof zh;

const DICTS: Record<Lang, Dict> = { zh, en };

export function getDict(lang: Lang): Dict {
  return DICTS[lang] ?? zh;
}

export function fmt(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, k) => (vars[k] !== undefined ? String(vars[k]) : `{${k}}`));
}
