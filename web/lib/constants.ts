export const STAGE_NAMES = ['Brief', 'Routes', 'Thermo', 'BFD', 'DWSIM PFD'] as const;

export const STAGE_DESCS = [
  'Product · capacity · feed · purity',
  'Chemistry options & tradeoffs',
  'Components & property package',
  'Block-level topology',
  'Simulation & export',
] as const;

export const STAGE_COLORS: Record<number, string> = {
  1: '#1e6fb5',
  2: '#7c3aed',
  3: '#0b7a6a',
  4: '#c4690a',
  5: '#1a3554',
};

export const MAX_REFINEMENTS = 5;

export const EXAMPLE_INPUT =
  'Produce 1,000 kg/hr of methanol from natural gas via steam reforming with 99.5 mol% purity at 50 bar synthesis pressure';
