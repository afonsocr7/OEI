# Stage 1: build
FROM node:20 AS build
WORKDIR /app
COPY package.json tsconfig.json ./
RUN npm install
COPY . .
CMD ["npm", "run", "dev"]

# Stage 2: serve
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]