-- CreateTable
CREATE TABLE `sp_users` (
    `id` VARCHAR(64) NOT NULL,
    `email` VARCHAR(191) NOT NULL,
    `name` VARCHAR(191) NOT NULL,
    `passwordHash` VARCHAR(191) NOT NULL,
    `role` ENUM('ADMIN', 'CUSTOMER') NOT NULL DEFAULT 'CUSTOMER',
    `disabled` BOOLEAN NOT NULL DEFAULT false,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    UNIQUE INDEX `sp_users_email_key`(`email`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_refresh_tokens` (
    `id` VARCHAR(64) NOT NULL,
    `userId` VARCHAR(64) NOT NULL,
    `tokenHash` VARCHAR(191) NOT NULL,
    `expiresAt` DATETIME(3) NOT NULL,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    UNIQUE INDEX `sp_refresh_tokens_tokenHash_key`(`tokenHash`),
    INDEX `sp_refresh_tokens_userId_idx`(`userId`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_homes` (
    `id` VARCHAR(64) NOT NULL,
    `name` VARCHAR(191) NOT NULL,
    `timezone` VARCHAR(191) NOT NULL DEFAULT 'Africa/Tunis',
    `currency` VARCHAR(191) NOT NULL DEFAULT 'TND',
    `tariffPerKwh` DOUBLE NOT NULL DEFAULT 0.176,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_home_members` (
    `homeId` VARCHAR(64) NOT NULL,
    `userId` VARCHAR(64) NOT NULL,
    `role` ENUM('OWNER', 'ADMIN', 'MEMBER') NOT NULL DEFAULT 'MEMBER',

    INDEX `sp_home_members_userId_idx`(`userId`),
    PRIMARY KEY (`homeId`, `userId`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_rooms` (
    `id` VARCHAR(64) NOT NULL,
    `homeId` VARCHAR(64) NOT NULL,
    `name` VARCHAR(191) NOT NULL,
    `icon` VARCHAR(191) NOT NULL DEFAULT 'sofa',
    `sort` INTEGER NOT NULL DEFAULT 0,

    INDEX `sp_rooms_homeId_idx`(`homeId`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_devices` (
    `id` VARCHAR(64) NOT NULL,
    `secretHash` VARCHAR(191) NOT NULL,
    `claimCode` VARCHAR(191) NOT NULL,
    `type` ENUM('PLUG', 'SWITCH', 'SWITCH_MULTI', 'DIMMER', 'RGB_LIGHT', 'CURTAIN', 'SENSOR_TH', 'ENERGY_METER') NOT NULL,
    `model` VARCHAR(191) NOT NULL,
    `channels` INTEGER NOT NULL DEFAULT 1,
    `firmware` VARCHAR(191) NULL,
    `homeId` VARCHAR(64) NULL,
    `roomId` VARCHAR(64) NULL,
    `name` VARCHAR(191) NULL,
    `online` BOOLEAN NOT NULL DEFAULT false,
    `lastSeenAt` DATETIME(3) NULL,
    `state` JSON NULL,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `claimedAt` DATETIME(3) NULL,

    INDEX `sp_devices_homeId_idx`(`homeId`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_timers` (
    `id` VARCHAR(64) NOT NULL,
    `deviceId` VARCHAR(64) NOT NULL,
    `at` VARCHAR(191) NOT NULL,
    `days` JSON NOT NULL,
    `command` JSON NOT NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT true,

    INDEX `sp_timers_deviceId_idx`(`deviceId`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_energy_readings` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `deviceId` VARCHAR(64) NOT NULL,
    `ts` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `powerW` DOUBLE NOT NULL,
    `voltageV` DOUBLE NULL,
    `currentA` DOUBLE NULL,

    INDEX `sp_energy_readings_deviceId_ts_idx`(`deviceId`, `ts`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_energy_hourly` (
    `deviceId` VARCHAR(64) NOT NULL,
    `hour` DATETIME(3) NOT NULL,
    `energyWh` DOUBLE NOT NULL DEFAULT 0,
    `maxPowerW` DOUBLE NOT NULL DEFAULT 0,

    INDEX `sp_energy_hourly_hour_idx`(`hour`),
    PRIMARY KEY (`deviceId`, `hour`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_scenes` (
    `id` VARCHAR(64) NOT NULL,
    `homeId` VARCHAR(64) NOT NULL,
    `name` VARCHAR(191) NOT NULL,
    `icon` VARCHAR(191) NOT NULL DEFAULT 'flash',
    `type` ENUM('MANUAL', 'AUTO') NOT NULL,
    `enabled` BOOLEAN NOT NULL DEFAULT true,
    `matchAll` BOOLEAN NOT NULL DEFAULT false,
    `conditions` JSON NOT NULL,
    `actions` JSON NOT NULL,
    `lastRunAt` DATETIME(3) NULL,
    `createdAt` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

    INDEX `sp_scenes_homeId_idx`(`homeId`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- CreateTable
CREATE TABLE `sp_scene_runs` (
    `id` VARCHAR(64) NOT NULL,
    `sceneId` VARCHAR(64) NOT NULL,
    `ts` DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    `trigger` VARCHAR(191) NOT NULL,
    `ok` BOOLEAN NOT NULL,
    `detail` TEXT NULL,

    INDEX `sp_scene_runs_sceneId_ts_idx`(`sceneId`, `ts`),
    PRIMARY KEY (`id`)
) DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- AddForeignKey
ALTER TABLE `sp_refresh_tokens` ADD CONSTRAINT `sp_refresh_tokens_userId_fkey` FOREIGN KEY (`userId`) REFERENCES `sp_users`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_home_members` ADD CONSTRAINT `sp_home_members_homeId_fkey` FOREIGN KEY (`homeId`) REFERENCES `sp_homes`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_home_members` ADD CONSTRAINT `sp_home_members_userId_fkey` FOREIGN KEY (`userId`) REFERENCES `sp_users`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_rooms` ADD CONSTRAINT `sp_rooms_homeId_fkey` FOREIGN KEY (`homeId`) REFERENCES `sp_homes`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_devices` ADD CONSTRAINT `sp_devices_homeId_fkey` FOREIGN KEY (`homeId`) REFERENCES `sp_homes`(`id`) ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_devices` ADD CONSTRAINT `sp_devices_roomId_fkey` FOREIGN KEY (`roomId`) REFERENCES `sp_rooms`(`id`) ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_timers` ADD CONSTRAINT `sp_timers_deviceId_fkey` FOREIGN KEY (`deviceId`) REFERENCES `sp_devices`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_energy_readings` ADD CONSTRAINT `sp_energy_readings_deviceId_fkey` FOREIGN KEY (`deviceId`) REFERENCES `sp_devices`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_energy_hourly` ADD CONSTRAINT `sp_energy_hourly_deviceId_fkey` FOREIGN KEY (`deviceId`) REFERENCES `sp_devices`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_scenes` ADD CONSTRAINT `sp_scenes_homeId_fkey` FOREIGN KEY (`homeId`) REFERENCES `sp_homes`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE `sp_scene_runs` ADD CONSTRAINT `sp_scene_runs_sceneId_fkey` FOREIGN KEY (`sceneId`) REFERENCES `sp_scenes`(`id`) ON DELETE CASCADE ON UPDATE CASCADE;
