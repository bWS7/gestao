import { createContext, useContext } from 'react';

// Lista de colegas da regional do usuário logado, disponibilizada para todos
// os campos "Responsável" dos relatórios (DynamicTable e inputs avulsos) sem
// precisar repassar a prop manualmente por cada um dos ~20 componentes de
// formulário. Populada uma vez por FormularioComercialModal.
const ColegasContext = createContext([]);

export const ColegasProvider = ColegasContext.Provider;

export function useColegas() {
  return useContext(ColegasContext);
}
