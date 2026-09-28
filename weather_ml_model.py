import os
import requests
import pandas as pd
from sklearn.ensemble import IsolationForest


def get_weather_and_detect(city="Kurukshetra"):
    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        raise ValueError("OpenWeather API key is not configured")

    url = "https://api.openweathermap.org/data/2.5/forecast"

    response = requests.get(
        url,
        params={
            "q": city,
            "appid": api_key,
            "units": "metric"
        },
        timeout=15
    )
    response.raise_for_status()

    forecast_list = response.json().get("list", [])
    weather_data = []

    for entry in forecast_list:
        weather_data.append({
            "DateTime": entry["dt_txt"],
            "Temperature": entry["main"]["temp"],
            "Humidity": entry["main"]["humidity"],
            "Pressure": entry["main"]["pressure"],
            "WindSpeed": entry["wind"]["speed"],
            "Rainfall": entry.get("rain", {}).get("3h", 0),
            "Weather": entry["weather"][0]["description"]
        })

    df = pd.DataFrame(weather_data)

    if len(df) < 2:
        raise ValueError("Not enough weather readings")

    features = [
        "Temperature", "Humidity", "Pressure",
        "WindSpeed", "Rainfall"
    ]

    df[features] = df[features].apply(
        pd.to_numeric, errors="coerce"
    )
    df.dropna(subset=features, inplace=True)

    if len(df) < 2:
        raise ValueError("Not enough valid readings")

    model = IsolationForest(
        contamination=0.1,
        random_state=42
    )

    df["Anomaly"] = model.fit_predict(
        df[features]
    ) == -1

    anomalies = df[df["Anomaly"]]

    return {
        "city": city,
        "total_records": len(df),
        "anomaly_count": len(anomalies),
        "weather_data": df.to_dict(orient="records")
    }