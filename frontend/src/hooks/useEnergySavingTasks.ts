import { useState, useEffect } from 'react';
import type { EnergyTask } from '../types/weather';

export const useEnergySavingTasks = () => {
  const [tasks, setTasks] = useState<EnergyTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchMockTasks = async () => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      setTasks([
        { id: '1', title: '白湯を飲む', description: '内臓を温めてホッと一息つきましょう' },
        { id: '2', title: '15分ボーッとする', description: '画面から目を離して、思考を停止します' },
        { id: '3', title: '深呼吸を3回', description: '自律神経を落ち着かせます' },
      ]);
      setIsLoading(false);
    };

    fetchMockTasks();
  }, []);

  return { tasks, isLoading };
};