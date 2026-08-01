import { useState, useEffect } from 'react';
import type { WeatherData } from '../types/weather';

const API_BASE = import.meta.env.VITE_API_BASE;

export const useWeatherStress = () => {
  const [data, setData] = useState<WeatherData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const fetchWeatherData = async (lat: number, lon: number) => {
      try {
        // バックエンドへ緯度経度を送信し、気圧などの情報をリクエスト
        const res = await fetch(`${API_BASE}/weather?lat=${lat}&lon=${lon}`);
        if (!res.ok) {
          throw new Error('バックエンドからのデータ取得に失敗しました');
        }
        const json = await res.json();
        setData(json);
      } catch (e) {
        console.warn('バックエンドAPI通信に失敗したため、モックデータを使用します:', e);
        // バックエンド未実装時のためのフォールバック
        setData({
          condition: '雨',
          pressure: 998, // 低気圧
          temperature: 19.0,
          stressLevel: 'HIGH',
        });
      } finally {
        setIsLoading(false);
      }
    };

    const handleLocationError = (err: GeolocationPositionError) => {
      console.warn('位置情報の取得に失敗しました。デフォルトの座標を使用します:', err);
      // 取得失敗時は東京の座標などをデフォルトとする
      fetchWeatherData(35.6812, 139.7671);
    };

    if ('geolocation' in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          fetchWeatherData(position.coords.latitude, position.coords.longitude);
        },
        handleLocationError,
        { timeout: 10000 }
      );
    } else {
      console.warn('このブラウザはGeolocationに対応していません。');
      fetchWeatherData(35.6812, 139.7671);
    }
  }, []);

  return { data, isLoading, error };
};