FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# Vite incrusta las env vars VITE_* en el build estático (no son configurables
# en runtime): deben pasarse como build arg, no como env del contenedor final.
ARG VITE_API_URL=http://localhost:8010
ENV VITE_API_URL=$VITE_API_URL
# Paquete de reproducibilidad: commit que se muestra en el pie (version.ts).
ARG VITE_GIT_COMMIT=desconocido
ENV VITE_GIT_COMMIT=$VITE_GIT_COMMIT
RUN npm run build

FROM node:20-slim
WORKDIR /app
RUN npm install -g serve
COPY --from=build /app/dist ./dist
EXPOSE 4173
CMD ["serve", "-s", "dist", "-l", "4173"]
