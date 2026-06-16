FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000',r=>process.exit(r.statusCode<500?0:1)).on('error',()=>process.exit(1))" || exit 1

CMD ["npm", "run", "start"]
