export type StressLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface WeatherData {
  condition: string;
  pressure: number;
  temperature: number;
  stressLevel: StressLevel; 
}

export interface EnergyTask {
  id: string;
  title: string;
  description?: string; // 説明は任意(オプショナル)
}