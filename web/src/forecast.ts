export const forecastModel = (id: string) =>
  ["uni.arima", "fc.var", "fc.eval"].includes(id);
