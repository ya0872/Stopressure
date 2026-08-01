import { useEffect, useState } from 'react';
import type { Coords } from '../api/client';

const SUPPORTED = 'geolocation' in navigator;

/**
 * 現在地を1度だけ取得する（docs/design.md §11 #7）。
 *
 * 取得できなければ null のまま。呼び出し側は null をそのままバックエンドへ渡し、
 * 既定地点（野々市）に任せる。ここで東京などの座標を埋めてしまうと、位置情報を
 * 拒否したユーザーに「別の土地の気圧」を本物の値として見せることになるため埋めない。
 *
 * 許可ダイアログの応答を待たせないこと。取得は非同期に進み、決着した時点で値が入る。
 */
export function useGeolocation(): Coords | null {
  const [coords, setCoords] = useState<Coords | null>(null);

  useEffect(() => {
    if (!SUPPORTED) {
      console.warn('このブラウザはGeolocationに対応していません。既定の地点を使用します。');
      return;
    }

    let cancelled = false;

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (cancelled) return;
        setCoords({ lat: position.coords.latitude, lon: position.coords.longitude });
      },
      (err) => {
        // 拒否・タイムアウトは異常ではない。既定地点で続行する
        console.warn('位置情報を取得できませんでした。既定の地点を使用します:', err.message);
      },
      { timeout: 10000, maximumAge: 10 * 60 * 1000 },
    );

    return () => {
      cancelled = true;
    };
  }, []);

  return coords;
}
