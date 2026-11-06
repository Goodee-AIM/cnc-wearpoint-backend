-- MySQL dump 10.13  Distrib 8.0.19, for Win64 (x86_64)
--
-- Host: 127.0.0.1    Database: mlflow
-- ------------------------------------------------------
-- Server version	8.4.13

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `alembic_version`
--

DROP TABLE IF EXISTS `alembic_version`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alembic_version` (
  `version_num` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`version_num`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `alembic_version`
--

LOCK TABLES `alembic_version` WRITE;
/*!40000 ALTER TABLE `alembic_version` DISABLE KEYS */;
/*!40000 ALTER TABLE `alembic_version` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `assessments`
--

DROP TABLE IF EXISTS `assessments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `assessments` (
  `assessment_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `trace_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `assessment_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `error` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `created_timestamp` bigint NOT NULL,
  `last_updated_timestamp` bigint NOT NULL,
  `source_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `source_id` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `run_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `span_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `rationale` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `overrides` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `valid` tinyint(1) NOT NULL,
  `assessment_metadata` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `experiment_id` int DEFAULT NULL,
  `trace_timestamp_ms` bigint DEFAULT NULL,
  `aggregate_value` double DEFAULT NULL,
  `is_numeric_value` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`assessment_id`),
  KEY `idx_assessments_exp_name_valid` (`experiment_id`,`name`,`valid`),
  KEY `idx_assessments_exp_trace_ts` (`experiment_id`,`trace_timestamp_ms`),
  KEY `idx_assessments_exp_trace_ts_name` (`experiment_id`,`trace_timestamp_ms`,`name`),
  KEY `index_assessments_assessment_type` (`assessment_type`),
  KEY `index_assessments_last_updated_timestamp` (`last_updated_timestamp`),
  KEY `index_assessments_run_id_created_timestamp` (`run_id`,`created_timestamp`),
  KEY `index_assessments_trace_id_created_timestamp` (`trace_id`,`created_timestamp`),
  CONSTRAINT `fk_assessments_trace_id` FOREIGN KEY (`trace_id`) REFERENCES `trace_info` (`request_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `assessments`
--

LOCK TABLES `assessments` WRITE;
/*!40000 ALTER TABLE `assessments` DISABLE KEYS */;
/*!40000 ALTER TABLE `assessments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `budget_policies`
--

DROP TABLE IF EXISTS `budget_policies`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `budget_policies` (
  `budget_policy_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `budget_unit` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `budget_amount` double NOT NULL,
  `duration_unit` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `duration_value` int NOT NULL,
  `target_scope` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `budget_action` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `target_value` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`budget_policy_id`),
  KEY `idx_budget_policies_target_value` (`target_value`),
  KEY `idx_budget_policies_workspace` (`workspace`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `budget_policies`
--

LOCK TABLES `budget_policies` WRITE;
/*!40000 ALTER TABLE `budget_policies` DISABLE KEYS */;
/*!40000 ALTER TABLE `budget_policies` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `datasets`
--

DROP TABLE IF EXISTS `datasets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `datasets` (
  `dataset_uuid` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `name` varchar(500) COLLATE utf8mb4_0900_bin NOT NULL,
  `digest` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `dataset_source_type` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `dataset_source` text COLLATE utf8mb4_0900_bin NOT NULL,
  `dataset_schema` text COLLATE utf8mb4_0900_bin,
  `dataset_profile` text COLLATE utf8mb4_0900_bin,
  PRIMARY KEY (`experiment_id`,`name`,`digest`),
  KEY `index_datasets_dataset_uuid` (`dataset_uuid`),
  KEY `index_datasets_experiment_id_dataset_source_type` (`experiment_id`,`dataset_source_type`),
  CONSTRAINT `fk_datasets_experiment_id_experiments` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 학습 데이터셋 메타데이터';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `datasets`
--

LOCK TABLES `datasets` WRITE;
/*!40000 ALTER TABLE `datasets` DISABLE KEYS */;
/*!40000 ALTER TABLE `datasets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoint_bindings`
--

DROP TABLE IF EXISTS `endpoint_bindings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `endpoint_bindings` (
  `endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `resource_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `resource_id` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_at` bigint NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `display_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`endpoint_id`,`resource_type`,`resource_id`),
  CONSTRAINT `fk_endpoint_bindings_endpoint_id` FOREIGN KEY (`endpoint_id`) REFERENCES `endpoints` (`endpoint_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoint_bindings`
--

LOCK TABLES `endpoint_bindings` WRITE;
/*!40000 ALTER TABLE `endpoint_bindings` DISABLE KEYS */;
/*!40000 ALTER TABLE `endpoint_bindings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoint_model_mappings`
--

DROP TABLE IF EXISTS `endpoint_model_mappings`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `endpoint_model_mappings` (
  `mapping_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `model_definition_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `weight` double NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `linkage_type` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'PRIMARY',
  `fallback_order` int DEFAULT NULL,
  PRIMARY KEY (`mapping_id`),
  UNIQUE KEY `unique_endpoint_model_linkage_mapping` (`endpoint_id`,`model_definition_id`,`linkage_type`),
  KEY `index_endpoint_model_mappings_endpoint_id` (`endpoint_id`),
  KEY `index_endpoint_model_mappings_model_definition_id` (`model_definition_id`),
  CONSTRAINT `fk_endpoint_model_mappings_endpoint_id` FOREIGN KEY (`endpoint_id`) REFERENCES `endpoints` (`endpoint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_endpoint_model_mappings_model_definition_id` FOREIGN KEY (`model_definition_id`) REFERENCES `model_definitions` (`model_definition_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoint_model_mappings`
--

LOCK TABLES `endpoint_model_mappings` WRITE;
/*!40000 ALTER TABLE `endpoint_model_mappings` DISABLE KEYS */;
/*!40000 ALTER TABLE `endpoint_model_mappings` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoint_tags`
--

DROP TABLE IF EXISTS `endpoint_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `endpoint_tags` (
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`endpoint_id`),
  KEY `index_endpoint_tags_endpoint_id` (`endpoint_id`),
  CONSTRAINT `fk_endpoint_tags_endpoint_id` FOREIGN KEY (`endpoint_id`) REFERENCES `endpoints` (`endpoint_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoint_tags`
--

LOCK TABLES `endpoint_tags` WRITE;
/*!40000 ALTER TABLE `endpoint_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `endpoint_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `endpoints`
--

DROP TABLE IF EXISTS `endpoints`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `endpoints` (
  `endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `routing_strategy` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `fallback_config_json` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `experiment_id` int DEFAULT NULL,
  `usage_tracking` tinyint(1) NOT NULL DEFAULT '0',
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`endpoint_id`),
  UNIQUE KEY `uq_endpoints_workspace_name` (`workspace`,`name`),
  KEY `idx_endpoints_workspace` (`workspace`),
  KEY `fk_endpoints_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_endpoints_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `endpoints`
--

LOCK TABLES `endpoints` WRITE;
/*!40000 ALTER TABLE `endpoints` DISABLE KEYS */;
/*!40000 ALTER TABLE `endpoints` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `entity_associations`
--

DROP TABLE IF EXISTS `entity_associations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `entity_associations` (
  `association_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `source_type` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `source_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `destination_type` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `destination_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_time` bigint DEFAULT NULL,
  PRIMARY KEY (`source_type`,`source_id`,`destination_type`,`destination_id`),
  KEY `index_entity_associations_association_id` (`association_id`),
  KEY `index_entity_associations_reverse_lookup` (`destination_type`,`destination_id`,`source_type`,`source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `entity_associations`
--

LOCK TABLES `entity_associations` WRITE;
/*!40000 ALTER TABLE `entity_associations` DISABLE KEYS */;
/*!40000 ALTER TABLE `entity_associations` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluation_dataset_records`
--

DROP TABLE IF EXISTS `evaluation_dataset_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_dataset_records` (
  `dataset_record_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `dataset_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `inputs` json NOT NULL,
  `expectations` json DEFAULT NULL,
  `tags` json DEFAULT NULL,
  `source` json DEFAULT NULL,
  `source_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source_type` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_time` bigint DEFAULT NULL,
  `last_update_time` bigint DEFAULT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `input_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `outputs` json DEFAULT NULL,
  PRIMARY KEY (`dataset_record_id`),
  UNIQUE KEY `unique_dataset_input` (`dataset_id`,`input_hash`),
  KEY `index_evaluation_dataset_records_dataset_id` (`dataset_id`),
  CONSTRAINT `fk_evaluation_dataset_records_dataset_id` FOREIGN KEY (`dataset_id`) REFERENCES `evaluation_datasets` (`dataset_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_dataset_records`
--

LOCK TABLES `evaluation_dataset_records` WRITE;
/*!40000 ALTER TABLE `evaluation_dataset_records` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_dataset_records` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluation_dataset_tags`
--

DROP TABLE IF EXISTS `evaluation_dataset_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_dataset_tags` (
  `dataset_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`dataset_id`,`key`),
  KEY `index_evaluation_dataset_tags_dataset_id` (`dataset_id`),
  CONSTRAINT `fk_evaluation_dataset_tags_dataset_id` FOREIGN KEY (`dataset_id`) REFERENCES `evaluation_datasets` (`dataset_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_dataset_tags`
--

LOCK TABLES `evaluation_dataset_tags` WRITE;
/*!40000 ALTER TABLE `evaluation_dataset_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_dataset_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `evaluation_datasets`
--

DROP TABLE IF EXISTS `evaluation_datasets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `evaluation_datasets` (
  `dataset_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `schema` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `profile` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `digest` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_time` bigint DEFAULT NULL,
  `last_update_time` bigint DEFAULT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`dataset_id`),
  KEY `idx_evaluation_datasets_workspace` (`workspace`),
  KEY `index_evaluation_datasets_created_time` (`created_time`),
  KEY `index_evaluation_datasets_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `evaluation_datasets`
--

LOCK TABLES `evaluation_datasets` WRITE;
/*!40000 ALTER TABLE `evaluation_datasets` DISABLE KEYS */;
/*!40000 ALTER TABLE `evaluation_datasets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `experiment_tags`
--

DROP TABLE IF EXISTS `experiment_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `experiment_tags` (
  `key` varchar(250) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` text COLLATE utf8mb4_0900_bin,
  `experiment_id` int NOT NULL,
  PRIMARY KEY (`key`,`experiment_id`),
  KEY `fk_experiment_tags_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_experiment_tags_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 실험 태그';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `experiment_tags`
--

LOCK TABLES `experiment_tags` WRITE;
/*!40000 ALTER TABLE `experiment_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `experiment_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `experiments`
--

DROP TABLE IF EXISTS `experiments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `experiments` (
  `experiment_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(256) COLLATE utf8mb4_0900_bin NOT NULL,
  `artifact_location` varchar(256) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `lifecycle_stage` varchar(32) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `creation_time` bigint DEFAULT NULL,
  `last_update_time` bigint DEFAULT NULL,
  `workspace` varchar(63) COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`experiment_id`),
  UNIQUE KEY `uq_experiments_workspace_name` (`workspace`,`name`),
  KEY `idx_experiments_workspace` (`workspace`),
  KEY `idx_experiments_workspace_creation_time` (`workspace`,`creation_time`),
  CONSTRAINT `experiments_lifecycle_stage` CHECK ((`lifecycle_stage` in (_utf8mb4'active',_utf8mb4'deleted')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 학습 실험';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `experiments`
--

LOCK TABLES `experiments` WRITE;
/*!40000 ALTER TABLE `experiments` DISABLE KEYS */;
/*!40000 ALTER TABLE `experiments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `guardrail_configs`
--

DROP TABLE IF EXISTS `guardrail_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `guardrail_configs` (
  `endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `guardrail_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `execution_order` int DEFAULT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`endpoint_id`,`guardrail_id`),
  KEY `idx_guardrail_configs_endpoint_id` (`endpoint_id`),
  KEY `idx_guardrail_configs_guardrail_id` (`guardrail_id`),
  CONSTRAINT `fk_guardrail_configs_endpoint_id` FOREIGN KEY (`endpoint_id`) REFERENCES `endpoints` (`endpoint_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_guardrail_configs_guardrail_id` FOREIGN KEY (`guardrail_id`) REFERENCES `guardrails` (`guardrail_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `guardrail_configs`
--

LOCK TABLES `guardrail_configs` WRITE;
/*!40000 ALTER TABLE `guardrail_configs` DISABLE KEYS */;
/*!40000 ALTER TABLE `guardrail_configs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `guardrails`
--

DROP TABLE IF EXISTS `guardrails`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `guardrails` (
  `guardrail_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `scorer_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `scorer_version` int NOT NULL,
  `stage` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `action` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `action_endpoint_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`guardrail_id`),
  KEY `idx_guardrails_scorer` (`scorer_id`,`scorer_version`),
  KEY `idx_guardrails_workspace` (`workspace`),
  KEY `fk_guardrails_action_endpoint_id` (`action_endpoint_id`),
  CONSTRAINT `fk_guardrails_action_endpoint_id` FOREIGN KEY (`action_endpoint_id`) REFERENCES `endpoints` (`endpoint_id`) ON DELETE SET NULL,
  CONSTRAINT `fk_guardrails_scorer_version` FOREIGN KEY (`scorer_id`, `scorer_version`) REFERENCES `scorer_versions` (`scorer_id`, `scorer_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `guardrails`
--

LOCK TABLES `guardrails` WRITE;
/*!40000 ALTER TABLE `guardrails` DISABLE KEYS */;
/*!40000 ALTER TABLE `guardrails` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `input_tags`
--

DROP TABLE IF EXISTS `input_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `input_tags` (
  `input_uuid` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(500) COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`input_uuid`,`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 입력 연결의 태그';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `input_tags`
--

LOCK TABLES `input_tags` WRITE;
/*!40000 ALTER TABLE `input_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `input_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `inputs`
--

DROP TABLE IF EXISTS `inputs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `inputs` (
  `input_uuid` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `source_type` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `source_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `destination_type` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `destination_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `step` bigint NOT NULL DEFAULT '0',
  PRIMARY KEY (`source_type`,`source_id`,`destination_type`,`destination_id`),
  KEY `index_inputs_destination_type_destination_id_source_type` (`destination_type`,`destination_id`,`source_type`),
  KEY `index_inputs_input_uuid` (`input_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 입력 자료와 사용 대상의 연결';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `inputs`
--

LOCK TABLES `inputs` WRITE;
/*!40000 ALTER TABLE `inputs` DISABLE KEYS */;
/*!40000 ALTER TABLE `inputs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `issue_categories`
--

DROP TABLE IF EXISTS `issue_categories`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `issue_categories` (
  `issue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `category_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `category` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`issue_id`,`category_hash`),
  KEY `index_issue_categories_hash` (`category_hash`),
  CONSTRAINT `fk_issue_categories_issue_id` FOREIGN KEY (`issue_id`) REFERENCES `issues` (`issue_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `issue_categories`
--

LOCK TABLES `issue_categories` WRITE;
/*!40000 ALTER TABLE `issue_categories` DISABLE KEYS */;
/*!40000 ALTER TABLE `issue_categories` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `issues`
--

DROP TABLE IF EXISTS `issues`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `issues` (
  `issue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `severity` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `root_causes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `source_run_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `categories` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `created_timestamp` bigint NOT NULL,
  `last_updated_timestamp` bigint NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_seen_timestamp` bigint DEFAULT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `metadata` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  PRIMARY KEY (`issue_id`),
  KEY `index_issues_experiment_id` (`experiment_id`),
  KEY `index_issues_experiment_last_seen` (`experiment_id`,`last_seen_timestamp`),
  KEY `index_issues_experiment_updated` (`experiment_id`,`last_updated_timestamp`),
  KEY `index_issues_source_run_id` (`source_run_id`),
  KEY `index_issues_status` (`status`),
  CONSTRAINT `fk_issues_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_issues_source_run_id` FOREIGN KEY (`source_run_id`) REFERENCES `runs` (`run_uuid`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `issues`
--

LOCK TABLES `issues` WRITE;
/*!40000 ALTER TABLE `issues` DISABLE KEYS */;
/*!40000 ALTER TABLE `issues` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `job_locks`
--

DROP TABLE IF EXISTS `job_locks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `job_locks` (
  `lock_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `job_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `acquired_at` bigint NOT NULL,
  PRIMARY KEY (`lock_key`),
  KEY `index_job_locks_job_id` (`job_id`),
  CONSTRAINT `fk_job_locks_job_id` FOREIGN KEY (`job_id`) REFERENCES `jobs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `job_locks`
--

LOCK TABLES `job_locks` WRITE;
/*!40000 ALTER TABLE `job_locks` DISABLE KEYS */;
/*!40000 ALTER TABLE `job_locks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `jobs`
--

DROP TABLE IF EXISTS `jobs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `jobs` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `creation_time` bigint NOT NULL,
  `job_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `params` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `timeout` double DEFAULT NULL,
  `status` int NOT NULL,
  `result` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `retry_count` int NOT NULL,
  `last_update_time` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `status_details` json DEFAULT NULL,
  `creator` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `executor_backend` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `lease_expires_at` bigint DEFAULT NULL,
  `status_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `progress` json DEFAULT NULL,
  `progress_updated_at` bigint DEFAULT NULL,
  `token_hash` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `scoped_permissions` json DEFAULT NULL,
  `next_attempt_at` bigint DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `index_jobs_name_status_creation_time` (`job_name`,`workspace`,`status`,`creation_time`),
  KEY `index_jobs_status_lease_expires_at` (`status`,`lease_expires_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `jobs`
--

LOCK TABLES `jobs` WRITE;
/*!40000 ALTER TABLE `jobs` DISABLE KEYS */;
/*!40000 ALTER TABLE `jobs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `label_schemas`
--

DROP TABLE IF EXISTS `label_schemas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `label_schemas` (
  `schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `type` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `instruction` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `enable_comment` tinyint(1) NOT NULL DEFAULT '0',
  `input_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `input_config` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_time` bigint NOT NULL,
  `last_update_time` bigint NOT NULL,
  `is_default` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`schema_id`),
  UNIQUE KEY `uq_label_schemas_exp_name` (`experiment_id`,`name`),
  KEY `index_label_schemas_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_label_schemas_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `label_schemas`
--

LOCK TABLES `label_schemas` WRITE;
/*!40000 ALTER TABLE `label_schemas` DISABLE KEYS */;
/*!40000 ALTER TABLE `label_schemas` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `latest_metrics`
--

DROP TABLE IF EXISTS `latest_metrics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `latest_metrics` (
  `key` varchar(250) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` double NOT NULL,
  `timestamp` bigint DEFAULT NULL,
  `step` bigint NOT NULL,
  `is_nan` tinyint(1) NOT NULL,
  `run_uuid` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`run_uuid`),
  KEY `index_latest_metrics_run_uuid` (`run_uuid`),
  CONSTRAINT `fk_latest_metrics_run_uuid` FOREIGN KEY (`run_uuid`) REFERENCES `runs` (`run_uuid`),
  CONSTRAINT `latest_metrics_is_nan` CHECK ((`is_nan` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow Run별 지표 최신 값';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `latest_metrics`
--

LOCK TABLES `latest_metrics` WRITE;
/*!40000 ALTER TABLE `latest_metrics` DISABLE KEYS */;
/*!40000 ALTER TABLE `latest_metrics` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logged_model_metrics`
--

DROP TABLE IF EXISTS `logged_model_metrics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logged_model_metrics` (
  `model_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `metric_name` varchar(500) COLLATE utf8mb4_0900_bin NOT NULL,
  `metric_timestamp_ms` bigint NOT NULL,
  `metric_step` bigint NOT NULL,
  `metric_value` double DEFAULT NULL,
  `experiment_id` int NOT NULL,
  `run_id` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  `dataset_uuid` varchar(36) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `dataset_name` varchar(500) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `dataset_digest` varchar(36) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`model_id`,`metric_name`,`metric_timestamp_ms`,`metric_step`,`run_id`),
  KEY `index_logged_model_metrics_model_id` (`model_id`),
  KEY `fk_logged_model_metrics_experiment_id` (`experiment_id`),
  KEY `fk_logged_model_metrics_run_id` (`run_id`),
  CONSTRAINT `fk_logged_model_metrics_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `fk_logged_model_metrics_model_id` FOREIGN KEY (`model_id`) REFERENCES `logged_models` (`model_id`) ON DELETE CASCADE,
  CONSTRAINT `fk_logged_model_metrics_run_id` FOREIGN KEY (`run_id`) REFERENCES `runs` (`run_uuid`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 저장 모델별 평가 지표';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logged_model_metrics`
--

LOCK TABLES `logged_model_metrics` WRITE;
/*!40000 ALTER TABLE `logged_model_metrics` DISABLE KEYS */;
/*!40000 ALTER TABLE `logged_model_metrics` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logged_model_params`
--

DROP TABLE IF EXISTS `logged_model_params`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logged_model_params` (
  `model_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `param_key` varchar(255) COLLATE utf8mb4_0900_bin NOT NULL,
  `param_value` text COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`model_id`,`param_key`),
  KEY `fk_logged_model_params_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_logged_model_params_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `fk_logged_model_params_model_id` FOREIGN KEY (`model_id`) REFERENCES `logged_models` (`model_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 저장 모델별 파라미터';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logged_model_params`
--

LOCK TABLES `logged_model_params` WRITE;
/*!40000 ALTER TABLE `logged_model_params` DISABLE KEYS */;
/*!40000 ALTER TABLE `logged_model_params` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logged_model_tags`
--

DROP TABLE IF EXISTS `logged_model_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logged_model_tags` (
  `model_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `tag_key` varchar(255) COLLATE utf8mb4_0900_bin NOT NULL,
  `tag_value` text COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`model_id`,`tag_key`),
  KEY `fk_logged_model_tags_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_logged_model_tags_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `fk_logged_model_tags_model_id` FOREIGN KEY (`model_id`) REFERENCES `logged_models` (`model_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 저장 모델별 태그';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logged_model_tags`
--

LOCK TABLES `logged_model_tags` WRITE;
/*!40000 ALTER TABLE `logged_model_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `logged_model_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `logged_models`
--

DROP TABLE IF EXISTS `logged_models`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `logged_models` (
  `model_id` varchar(36) COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `name` varchar(500) COLLATE utf8mb4_0900_bin NOT NULL,
  `artifact_location` varchar(1000) COLLATE utf8mb4_0900_bin NOT NULL,
  `creation_timestamp_ms` bigint NOT NULL,
  `last_updated_timestamp_ms` bigint NOT NULL,
  `status` int NOT NULL,
  `lifecycle_stage` varchar(32) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `model_type` varchar(500) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source_run_id` varchar(32) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status_message` varchar(1000) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`model_id`),
  KEY `fk_logged_models_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_logged_models_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE,
  CONSTRAINT `logged_models_lifecycle_stage_check` CHECK ((`lifecycle_stage` in (_utf8mb4'active',_utf8mb4'deleted')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 저장 모델 메타데이터';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `logged_models`
--

LOCK TABLES `logged_models` WRITE;
/*!40000 ALTER TABLE `logged_models` DISABLE KEYS */;
/*!40000 ALTER TABLE `logged_models` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_access_endpoints`
--

DROP TABLE IF EXISTS `mcp_access_endpoints`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_access_endpoints` (
  `id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `server_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `server_version` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `server_alias` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `url` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `transport_type` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'streamable-http',
  `created_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_at` bigint NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_mcp_access_endpoints_alias` (`workspace`,`server_name`,`server_alias`),
  KEY `ix_mcp_access_endpoints_server_name` (`workspace`,`server_name`),
  KEY `ix_mcp_access_endpoints_version` (`workspace`,`server_name`,`server_version`),
  CONSTRAINT `mcp_access_endpoints_server_fkey` FOREIGN KEY (`workspace`, `server_name`) REFERENCES `mcp_servers` (`workspace`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_access_endpoints`
--

LOCK TABLES `mcp_access_endpoints` WRITE;
/*!40000 ALTER TABLE `mcp_access_endpoints` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_access_endpoints` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_server_aliases`
--

DROP TABLE IF EXISTS `mcp_server_aliases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_server_aliases` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `alias` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`workspace`,`name`,`alias`),
  CONSTRAINT `mcp_server_aliases_server_fkey` FOREIGN KEY (`workspace`, `name`) REFERENCES `mcp_servers` (`workspace`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_server_aliases`
--

LOCK TABLES `mcp_server_aliases` WRITE;
/*!40000 ALTER TABLE `mcp_server_aliases` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_server_aliases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_server_tags`
--

DROP TABLE IF EXISTS `mcp_server_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_server_tags` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`workspace`,`name`,`key`),
  CONSTRAINT `mcp_server_tags_server_fkey` FOREIGN KEY (`workspace`, `name`) REFERENCES `mcp_servers` (`workspace`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_server_tags`
--

LOCK TABLES `mcp_server_tags` WRITE;
/*!40000 ALTER TABLE `mcp_server_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_server_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_server_version_tags`
--

DROP TABLE IF EXISTS `mcp_server_version_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_server_version_tags` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`workspace`,`name`,`version`,`key`),
  CONSTRAINT `mcp_server_version_tags_version_fkey` FOREIGN KEY (`workspace`, `name`, `version`) REFERENCES `mcp_server_versions` (`workspace`, `name`, `version`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_server_version_tags`
--

LOCK TABLES `mcp_server_version_tags` WRITE;
/*!40000 ALTER TABLE `mcp_server_version_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_server_version_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_server_versions`
--

DROP TABLE IF EXISTS `mcp_server_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_server_versions` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version_major` int NOT NULL,
  `version_minor` int NOT NULL,
  `version_patch` int NOT NULL,
  `version_prerelease_sort_key` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `server_json` json NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'draft',
  `tools` json DEFAULT NULL,
  `source` varchar(512) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `connect_options` json DEFAULT NULL,
  `created_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_at` bigint NOT NULL,
  PRIMARY KEY (`workspace`,`name`,`version`),
  KEY `idx_mcp_server_versions_latest` (`workspace`,`name`,`status`,`version_major` DESC,`version_minor` DESC,`version_patch` DESC),
  CONSTRAINT `mcp_server_versions_server_fkey` FOREIGN KEY (`workspace`, `name`) REFERENCES `mcp_servers` (`workspace`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_server_versions`
--

LOCK TABLES `mcp_server_versions` WRITE;
/*!40000 ALTER TABLE `mcp_server_versions` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_server_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `mcp_servers`
--

DROP TABLE IF EXISTS `mcp_servers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `mcp_servers` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `display_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `icons` json DEFAULT NULL,
  `created_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_at` bigint NOT NULL,
  PRIMARY KEY (`workspace`,`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `mcp_servers`
--

LOCK TABLES `mcp_servers` WRITE;
/*!40000 ALTER TABLE `mcp_servers` DISABLE KEYS */;
/*!40000 ALTER TABLE `mcp_servers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `metrics`
--

DROP TABLE IF EXISTS `metrics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `metrics` (
  `key` varchar(250) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` double NOT NULL,
  `timestamp` bigint NOT NULL,
  `run_uuid` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  `step` bigint NOT NULL DEFAULT '0',
  `is_nan` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`key`,`timestamp`,`step`,`run_uuid`,`value`,`is_nan`),
  KEY `index_metrics_run_uuid` (`run_uuid`),
  KEY `index_metrics_run_uuid_key_step` (`run_uuid`,`key`,`step`),
  CONSTRAINT `fk_metrics_run_uuid` FOREIGN KEY (`run_uuid`) REFERENCES `runs` (`run_uuid`),
  CONSTRAINT `metrics_is_nan` CHECK ((`is_nan` in (0,1)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow Run별 평가 지표 전체 이력';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `metrics`
--

LOCK TABLES `metrics` WRITE;
/*!40000 ALTER TABLE `metrics` DISABLE KEYS */;
/*!40000 ALTER TABLE `metrics` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `model_definitions`
--

DROP TABLE IF EXISTS `model_definitions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_definitions` (
  `model_definition_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `secret_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `provider` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `model_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`model_definition_id`),
  UNIQUE KEY `uq_model_definitions_workspace_name` (`workspace`,`name`),
  KEY `index_model_definitions_provider` (`provider`),
  KEY `index_model_definitions_secret_id` (`secret_id`),
  KEY `idx_model_definitions_workspace` (`workspace`),
  CONSTRAINT `fk_model_definitions_secret_id` FOREIGN KEY (`secret_id`) REFERENCES `secrets` (`secret_id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_definitions`
--

LOCK TABLES `model_definitions` WRITE;
/*!40000 ALTER TABLE `model_definitions` DISABLE KEYS */;
/*!40000 ALTER TABLE `model_definitions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `model_version_tags`
--

DROP TABLE IF EXISTS `model_version_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_version_tags` (
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`workspace`,`key`,`name`,`version`),
  KEY `idx_model_version_tags_workspace_name_version` (`workspace`,`name`,`version`),
  CONSTRAINT `fk_model_version_tags_model_versions` FOREIGN KEY (`workspace`, `name`, `version`) REFERENCES `model_versions` (`workspace`, `name`, `version`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_version_tags`
--

LOCK TABLES `model_version_tags` WRITE;
/*!40000 ALTER TABLE `model_version_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `model_version_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `model_versions`
--

DROP TABLE IF EXISTS `model_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_versions` (
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  `creation_time` bigint DEFAULT NULL,
  `last_updated_time` bigint DEFAULT NULL,
  `description` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `user_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `current_stage` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `run_id` varchar(32) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status_message` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `run_link` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `storage_location` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`workspace`,`name`,`version`),
  CONSTRAINT `fk_model_versions_registered_models` FOREIGN KEY (`workspace`, `name`) REFERENCES `registered_models` (`workspace`, `name`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_versions`
--

LOCK TABLES `model_versions` WRITE;
/*!40000 ALTER TABLE `model_versions` DISABLE KEYS */;
/*!40000 ALTER TABLE `model_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `online_scoring_configs`
--

DROP TABLE IF EXISTS `online_scoring_configs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `online_scoring_configs` (
  `online_scoring_config_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `scorer_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `sample_rate` double NOT NULL,
  `experiment_id` int NOT NULL,
  `filter_string` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  PRIMARY KEY (`online_scoring_config_id`),
  KEY `fk_online_scoring_configs_scorer_id` (`scorer_id`),
  KEY `fk_online_scoring_configs_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_online_scoring_configs_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `fk_online_scoring_configs_scorer_id` FOREIGN KEY (`scorer_id`) REFERENCES `scorers` (`scorer_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `online_scoring_configs`
--

LOCK TABLES `online_scoring_configs` WRITE;
/*!40000 ALTER TABLE `online_scoring_configs` DISABLE KEYS */;
/*!40000 ALTER TABLE `online_scoring_configs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `params`
--

DROP TABLE IF EXISTS `params`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `params` (
  `key` varchar(250) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(8000) COLLATE utf8mb4_0900_bin NOT NULL,
  `run_uuid` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`run_uuid`),
  KEY `index_params_run_uuid` (`run_uuid`),
  CONSTRAINT `fk_params_run_uuid` FOREIGN KEY (`run_uuid`) REFERENCES `runs` (`run_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow Run별 학습 파라미터';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `params`
--

LOCK TABLES `params` WRITE;
/*!40000 ALTER TABLE `params` DISABLE KEYS */;
/*!40000 ALTER TABLE `params` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `registered_model_aliases`
--

DROP TABLE IF EXISTS `registered_model_aliases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `registered_model_aliases` (
  `alias` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`workspace`,`name`,`alias`),
  CONSTRAINT `fk_registered_model_aliases_registered_models` FOREIGN KEY (`workspace`, `name`) REFERENCES `registered_models` (`workspace`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `registered_model_aliases`
--

LOCK TABLES `registered_model_aliases` WRITE;
/*!40000 ALTER TABLE `registered_model_aliases` DISABLE KEYS */;
/*!40000 ALTER TABLE `registered_model_aliases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `registered_model_tags`
--

DROP TABLE IF EXISTS `registered_model_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `registered_model_tags` (
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(5000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`workspace`,`key`,`name`),
  KEY `idx_registered_model_tags_workspace_name` (`workspace`,`name`),
  CONSTRAINT `fk_registered_model_tags_registered_models` FOREIGN KEY (`workspace`, `name`) REFERENCES `registered_models` (`workspace`, `name`) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `registered_model_tags`
--

LOCK TABLES `registered_model_tags` WRITE;
/*!40000 ALTER TABLE `registered_model_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `registered_model_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `registered_models`
--

DROP TABLE IF EXISTS `registered_models`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `registered_models` (
  `name` varchar(256) COLLATE utf8mb4_0900_bin NOT NULL,
  `creation_time` bigint DEFAULT NULL,
  `last_updated_time` bigint DEFAULT NULL,
  `description` varchar(5000) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `workspace` varchar(63) COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`workspace`,`name`),
  KEY `idx_registered_models_workspace` (`workspace`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 레지스트리 등록 모델';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `registered_models`
--

LOCK TABLES `registered_models` WRITE;
/*!40000 ALTER TABLE `registered_models` DISABLE KEYS */;
/*!40000 ALTER TABLE `registered_models` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `review_queue_items`
--

DROP TABLE IF EXISTS `review_queue_items`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `review_queue_items` (
  `queue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `item_type` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `item_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `status` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `completed_by` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `completed_time_ms` bigint DEFAULT NULL,
  `creation_time_ms` bigint NOT NULL,
  `last_update_time_ms` bigint NOT NULL,
  PRIMARY KEY (`queue_id`,`item_id`),
  KEY `index_review_queue_items_item_id` (`item_id`),
  KEY `index_review_queue_items_queue_id_status` (`queue_id`,`status`),
  CONSTRAINT `fk_review_queue_items_queue_id` FOREIGN KEY (`queue_id`) REFERENCES `review_queues` (`queue_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `review_queue_items`
--

LOCK TABLES `review_queue_items` WRITE;
/*!40000 ALTER TABLE `review_queue_items` DISABLE KEYS */;
/*!40000 ALTER TABLE `review_queue_items` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `review_queue_label_schemas`
--

DROP TABLE IF EXISTS `review_queue_label_schemas`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `review_queue_label_schemas` (
  `queue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `schema_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`queue_id`,`schema_id`),
  KEY `index_review_queue_label_schemas_schema_id` (`schema_id`),
  CONSTRAINT `fk_review_queue_label_schemas_queue_id` FOREIGN KEY (`queue_id`) REFERENCES `review_queues` (`queue_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `review_queue_label_schemas`
--

LOCK TABLES `review_queue_label_schemas` WRITE;
/*!40000 ALTER TABLE `review_queue_label_schemas` DISABLE KEYS */;
/*!40000 ALTER TABLE `review_queue_label_schemas` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `review_queue_users`
--

DROP TABLE IF EXISTS `review_queue_users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `review_queue_users` (
  `queue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `user_id` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`queue_id`,`user_id`),
  KEY `index_review_queue_users_user_id` (`user_id`),
  CONSTRAINT `fk_review_queue_users_queue_id` FOREIGN KEY (`queue_id`) REFERENCES `review_queues` (`queue_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `review_queue_users`
--

LOCK TABLES `review_queue_users` WRITE;
/*!40000 ALTER TABLE `review_queue_users` DISABLE KEYS */;
/*!40000 ALTER TABLE `review_queue_users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `review_queues`
--

DROP TABLE IF EXISTS `review_queues`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `review_queues` (
  `queue_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `queue_type` varchar(16) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `creation_time_ms` bigint NOT NULL,
  `last_update_time_ms` bigint NOT NULL,
  `name_key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`queue_id`),
  UNIQUE KEY `uq_review_queues_experiment_name_key` (`experiment_id`,`name_key`),
  KEY `index_review_queues_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_review_queues_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `review_queues`
--

LOCK TABLES `review_queues` WRITE;
/*!40000 ALTER TABLE `review_queues` DISABLE KEYS */;
/*!40000 ALTER TABLE `review_queues` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `runs`
--

DROP TABLE IF EXISTS `runs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `runs` (
  `run_uuid` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(250) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source_type` varchar(20) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source_name` varchar(500) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `entry_point_name` varchar(50) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `user_id` varchar(256) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status` varchar(9) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `start_time` bigint DEFAULT NULL,
  `end_time` bigint DEFAULT NULL,
  `source_version` varchar(50) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `lifecycle_stage` varchar(20) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `artifact_uri` varchar(200) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `experiment_id` int DEFAULT NULL,
  `deleted_time` bigint DEFAULT NULL,
  PRIMARY KEY (`run_uuid`),
  KEY `fk_runs_experiment_id` (`experiment_id`),
  CONSTRAINT `fk_runs_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `runs_lifecycle_stage` CHECK ((`lifecycle_stage` in (_utf8mb4'active',_utf8mb4'deleted'))),
  CONSTRAINT `runs_source_type` CHECK ((`source_type` in (_utf8mb4'NOTEBOOK',_utf8mb4'JOB',_utf8mb4'LOCAL',_utf8mb4'UNKNOWN',_utf8mb4'PROJECT'))),
  CONSTRAINT `runs_status` CHECK ((`status` in (_utf8mb4'SCHEDULED',_utf8mb4'FAILED',_utf8mb4'FINISHED',_utf8mb4'RUNNING',_utf8mb4'KILLED')))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 개별 학습 실행';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `runs`
--

LOCK TABLES `runs` WRITE;
/*!40000 ALTER TABLE `runs` DISABLE KEYS */;
/*!40000 ALTER TABLE `runs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scheduler_leases`
--

DROP TABLE IF EXISTS `scheduler_leases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scheduler_leases` (
  `lease_key` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `acquired_at` bigint NOT NULL,
  `ttl_seconds` int NOT NULL,
  PRIMARY KEY (`lease_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scheduler_leases`
--

LOCK TABLES `scheduler_leases` WRITE;
/*!40000 ALTER TABLE `scheduler_leases` DISABLE KEYS */;
/*!40000 ALTER TABLE `scheduler_leases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scorer_versions`
--

DROP TABLE IF EXISTS `scorer_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scorer_versions` (
  `scorer_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `scorer_version` int NOT NULL,
  `serialized_scorer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `creation_time` bigint DEFAULT NULL,
  PRIMARY KEY (`scorer_id`,`scorer_version`),
  KEY `index_scorer_versions_scorer_id` (`scorer_id`),
  CONSTRAINT `fk_scorer_versions_scorer_id` FOREIGN KEY (`scorer_id`) REFERENCES `scorers` (`scorer_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scorer_versions`
--

LOCK TABLES `scorer_versions` WRITE;
/*!40000 ALTER TABLE `scorer_versions` DISABLE KEYS */;
/*!40000 ALTER TABLE `scorer_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `scorers`
--

DROP TABLE IF EXISTS `scorers`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `scorers` (
  `experiment_id` int NOT NULL,
  `scorer_name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `scorer_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`scorer_id`),
  UNIQUE KEY `index_scorers_experiment_id_scorer_name` (`experiment_id`,`scorer_name`),
  CONSTRAINT `fk_scorers_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `scorers`
--

LOCK TABLES `scorers` WRITE;
/*!40000 ALTER TABLE `scorers` DISABLE KEYS */;
/*!40000 ALTER TABLE `scorers` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `secrets`
--

DROP TABLE IF EXISTS `secrets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `secrets` (
  `secret_id` varchar(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `secret_name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `encrypted_value` blob NOT NULL,
  `wrapped_dek` blob NOT NULL,
  `kek_version` int NOT NULL,
  `masked_value` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `provider` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `auth_config` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `created_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_by` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_at` bigint NOT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`secret_id`),
  UNIQUE KEY `uq_secrets_workspace_secret_name` (`workspace`,`secret_name`),
  KEY `idx_secrets_workspace` (`workspace`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `secrets`
--

LOCK TABLES `secrets` WRITE;
/*!40000 ALTER TABLE `secrets` DISABLE KEYS */;
/*!40000 ALTER TABLE `secrets` ENABLE KEYS */;
UNLOCK TABLES;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = latin1 */ ;
/*!50003 SET character_set_results = latin1 */ ;
/*!50003 SET collation_connection  = latin1_swedish_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
/*!50003 CREATE*/ /*!50017 DEFINER=`root`@`localhost`*/ /*!50003 TRIGGER `prevent_secrets_aad_mutation` BEFORE UPDATE ON `secrets` FOR EACH ROW BEGIN
    IF NOT (OLD.secret_id <=> NEW.secret_id)
       OR NOT (OLD.secret_name <=> NEW.secret_name)
    THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'secret_id and secret_name are immutable (used as AAD in encryption)';
    END IF;
END */;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;

--
-- Table structure for table `skill_aliases`
--

DROP TABLE IF EXISTS `skill_aliases`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_aliases` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `organization` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT '',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `alias` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  PRIMARY KEY (`workspace`,`organization`,`name`,`alias`),
  CONSTRAINT `skill_aliases_skill_fkey` FOREIGN KEY (`workspace`, `organization`, `name`) REFERENCES `skills` (`workspace`, `organization`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_aliases`
--

LOCK TABLES `skill_aliases` WRITE;
/*!40000 ALTER TABLE `skill_aliases` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_aliases` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_tags`
--

DROP TABLE IF EXISTS `skill_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_tags` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `organization` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT '',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  PRIMARY KEY (`workspace`,`organization`,`name`,`key`),
  CONSTRAINT `skill_tags_skill_fkey` FOREIGN KEY (`workspace`, `organization`, `name`) REFERENCES `skills` (`workspace`, `organization`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_tags`
--

LOCK TABLES `skill_tags` WRITE;
/*!40000 ALTER TABLE `skill_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_version_tags`
--

DROP TABLE IF EXISTS `skill_version_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_version_tags` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `organization` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT '',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  PRIMARY KEY (`workspace`,`organization`,`name`,`version`,`key`),
  CONSTRAINT `skill_version_tags_version_fkey` FOREIGN KEY (`workspace`, `organization`, `name`, `version`) REFERENCES `skill_versions` (`workspace`, `organization`, `name`, `version`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_version_tags`
--

LOCK TABLES `skill_version_tags` WRITE;
/*!40000 ALTER TABLE `skill_version_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_version_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skill_versions`
--

DROP TABLE IF EXISTS `skill_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skill_versions` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `organization` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT '',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `version` int NOT NULL,
  `source_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `source` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `ref` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `subpath` varchar(2048) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `digest` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'active',
  `created_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_at` bigint NOT NULL,
  PRIMARY KEY (`workspace`,`organization`,`name`,`version`),
  KEY `ix_skill_versions_digest` (`workspace`,`organization`,`name`,`digest`),
  KEY `ix_skill_versions_latest_lookup` (`workspace`,`organization`,`name`,`status`,`version`),
  CONSTRAINT `skill_versions_skill_fkey` FOREIGN KEY (`workspace`, `organization`, `name`) REFERENCES `skills` (`workspace`, `organization`, `name`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skill_versions`
--

LOCK TABLES `skill_versions` WRITE;
/*!40000 ALTER TABLE `skill_versions` DISABLE KEYS */;
/*!40000 ALTER TABLE `skill_versions` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `skills`
--

DROP TABLE IF EXISTS `skills`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `skills` (
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  `organization` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT '',
  `name` varchar(128) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `description` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `icons` json DEFAULT NULL,
  `search_text` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `created_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `last_updated_by` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `created_at` bigint NOT NULL,
  `last_updated_at` bigint NOT NULL,
  PRIMARY KEY (`workspace`,`organization`,`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `skills`
--

LOCK TABLES `skills` WRITE;
/*!40000 ALTER TABLE `skills` DISABLE KEYS */;
/*!40000 ALTER TABLE `skills` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `span_metrics`
--

DROP TABLE IF EXISTS `span_metrics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `span_metrics` (
  `trace_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `span_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` double DEFAULT NULL,
  PRIMARY KEY (`trace_id`,`span_id`,`key`),
  KEY `index_span_metrics_trace_id_span_id` (`trace_id`,`span_id`),
  CONSTRAINT `fk_span_metrics_span` FOREIGN KEY (`trace_id`, `span_id`) REFERENCES `spans` (`trace_id`, `span_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `span_metrics`
--

LOCK TABLES `span_metrics` WRITE;
/*!40000 ALTER TABLE `span_metrics` DISABLE KEYS */;
/*!40000 ALTER TABLE `span_metrics` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `spans`
--

DROP TABLE IF EXISTS `spans`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `spans` (
  `trace_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `span_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `parent_span_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `name` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin,
  `type` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `start_time_unix_nano` bigint NOT NULL,
  `end_time_unix_nano` bigint DEFAULT NULL,
  `duration_ns` bigint GENERATED ALWAYS AS ((`end_time_unix_nano` - `start_time_unix_nano`)) STORED,
  `content` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `input_cost` double DEFAULT NULL,
  `output_cost` double DEFAULT NULL,
  `total_cost` double DEFAULT NULL,
  `model_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `model_provider` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`trace_id`,`span_id`),
  KEY `idx_spans_cost_exp_time_cover` (`experiment_id`,`start_time_unix_nano`),
  KEY `idx_spans_cost_trace_time_cover` (`trace_id`,`start_time_unix_nano`),
  KEY `index_spans_experiment_id_duration` (`experiment_id`,`duration_ns`),
  KEY `index_spans_experiment_id_start_time` (`experiment_id`,`start_time_unix_nano`),
  KEY `index_spans_experiment_id_status_type` (`experiment_id`,`status`,`type`),
  KEY `index_spans_experiment_id_type_status` (`experiment_id`,`type`,`status`),
  CONSTRAINT `fk_spans_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`),
  CONSTRAINT `fk_spans_trace_id` FOREIGN KEY (`trace_id`) REFERENCES `trace_info` (`request_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `spans`
--

LOCK TABLES `spans` WRITE;
/*!40000 ALTER TABLE `spans` DISABLE KEYS */;
/*!40000 ALTER TABLE `spans` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sql_assessment_daily_rollups`
--

DROP TABLE IF EXISTS `sql_assessment_daily_rollups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sql_assessment_daily_rollups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `experiment_id` int NOT NULL,
  `rollup_day` date NOT NULL,
  `metric_name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `grouping_set` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `sample_count` bigint NOT NULL,
  `sum_value` double DEFAULT NULL,
  `min_value` double DEFAULT NULL,
  `max_value` double DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_assessment_rollups_lookup` (`experiment_id`,`rollup_day`,`metric_name`,`grouping_set`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sql_assessment_daily_rollups`
--

LOCK TABLES `sql_assessment_daily_rollups` WRITE;
/*!40000 ALTER TABLE `sql_assessment_daily_rollups` DISABLE KEYS */;
/*!40000 ALTER TABLE `sql_assessment_daily_rollups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sql_span_cost_daily_rollups`
--

DROP TABLE IF EXISTS `sql_span_cost_daily_rollups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sql_span_cost_daily_rollups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `experiment_id` int NOT NULL,
  `rollup_day` date NOT NULL,
  `metric_name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `grouping_set` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `model_name` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `model_provider` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `sample_count` bigint NOT NULL,
  `sum_value` double DEFAULT NULL,
  `min_value` double DEFAULT NULL,
  `max_value` double DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_span_cost_rollups_lookup` (`experiment_id`,`rollup_day`,`metric_name`,`grouping_set`,`model_name`(200),`model_provider`(200))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin ROW_FORMAT=DYNAMIC;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sql_span_cost_daily_rollups`
--

LOCK TABLES `sql_span_cost_daily_rollups` WRITE;
/*!40000 ALTER TABLE `sql_span_cost_daily_rollups` DISABLE KEYS */;
/*!40000 ALTER TABLE `sql_span_cost_daily_rollups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sql_trace_metric_daily_rollups`
--

DROP TABLE IF EXISTS `sql_trace_metric_daily_rollups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sql_trace_metric_daily_rollups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `experiment_id` int NOT NULL,
  `rollup_day` date NOT NULL,
  `metric_name` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `grouping_set` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `trace_status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `sample_count` bigint NOT NULL,
  `sum_value` double DEFAULT NULL,
  `min_value` double DEFAULT NULL,
  `max_value` double DEFAULT NULL,
  `p50_value` double DEFAULT NULL,
  `p90_value` double DEFAULT NULL,
  `p99_value` double DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_trace_rollups_lookup` (`experiment_id`,`rollup_day`,`metric_name`,`grouping_set`,`trace_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sql_trace_metric_daily_rollups`
--

LOCK TABLES `sql_trace_metric_daily_rollups` WRITE;
/*!40000 ALTER TABLE `sql_trace_metric_daily_rollups` DISABLE KEYS */;
/*!40000 ALTER TABLE `sql_trace_metric_daily_rollups` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `sql_trace_rollup_rebuild_queue`
--

DROP TABLE IF EXISTS `sql_trace_rollup_rebuild_queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sql_trace_rollup_rebuild_queue` (
  `experiment_id` int NOT NULL,
  `rollup_day` date NOT NULL,
  `rollup_family` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`experiment_id`,`rollup_day`,`rollup_family`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `sql_trace_rollup_rebuild_queue`
--

LOCK TABLES `sql_trace_rollup_rebuild_queue` WRITE;
/*!40000 ALTER TABLE `sql_trace_rollup_rebuild_queue` DISABLE KEYS */;
/*!40000 ALTER TABLE `sql_trace_rollup_rebuild_queue` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tags`
--

DROP TABLE IF EXISTS `tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tags` (
  `key` varchar(250) COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(8000) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `run_uuid` varchar(32) COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`run_uuid`),
  KEY `index_tags_run_uuid` (`run_uuid`),
  CONSTRAINT `fk_tags_run_uuid` FOREIGN KEY (`run_uuid`) REFERENCES `runs` (`run_uuid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow Run별 태그';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tags`
--

LOCK TABLES `tags` WRITE;
/*!40000 ALTER TABLE `tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `trace_info`
--

DROP TABLE IF EXISTS `trace_info`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `trace_info` (
  `request_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `experiment_id` int NOT NULL,
  `timestamp_ms` bigint NOT NULL,
  `execution_time_ms` bigint DEFAULT NULL,
  `status` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `client_request_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `request_preview` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `response_preview` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `db_payload_generation` int NOT NULL DEFAULT '0',
  `trace_name` varchar(4096) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `session_id` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `input_tokens` bigint DEFAULT NULL,
  `output_tokens` bigint DEFAULT NULL,
  `total_tokens` bigint DEFAULT NULL,
  `cache_read_input_tokens` bigint DEFAULT NULL,
  `cache_creation_input_tokens` bigint DEFAULT NULL,
  `cache_creation_input_tokens_above_1hr` bigint DEFAULT NULL,
  `input_cost` double DEFAULT NULL,
  `output_cost` double DEFAULT NULL,
  `total_cost` double DEFAULT NULL,
  PRIMARY KEY (`request_id`),
  KEY `index_trace_info_experiment_id_session_id` (`experiment_id`,`session_id`),
  KEY `index_trace_info_experiment_id_timestamp_ms` (`experiment_id`,`timestamp_ms`),
  KEY `index_trace_info_timestamp_ms_request_id` (`timestamp_ms`,`request_id`),
  CONSTRAINT `fk_trace_info_experiment_id` FOREIGN KEY (`experiment_id`) REFERENCES `experiments` (`experiment_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `trace_info`
--

LOCK TABLES `trace_info` WRITE;
/*!40000 ALTER TABLE `trace_info` DISABLE KEYS */;
/*!40000 ALTER TABLE `trace_info` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `trace_metrics`
--

DROP TABLE IF EXISTS `trace_metrics`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `trace_metrics` (
  `request_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` double DEFAULT NULL,
  PRIMARY KEY (`request_id`,`key`),
  KEY `index_trace_metrics_request_id` (`request_id`),
  CONSTRAINT `fk_trace_metrics_request_id` FOREIGN KEY (`request_id`) REFERENCES `trace_info` (`request_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `trace_metrics`
--

LOCK TABLES `trace_metrics` WRITE;
/*!40000 ALTER TABLE `trace_metrics` DISABLE KEYS */;
/*!40000 ALTER TABLE `trace_metrics` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `trace_request_metadata`
--

DROP TABLE IF EXISTS `trace_request_metadata`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `trace_request_metadata` (
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(8000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `request_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`request_id`),
  KEY `index_trace_request_metadata_request_id` (`request_id`),
  CONSTRAINT `fk_trace_request_metadata_request_id` FOREIGN KEY (`request_id`) REFERENCES `trace_info` (`request_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `trace_request_metadata`
--

LOCK TABLES `trace_request_metadata` WRITE;
/*!40000 ALTER TABLE `trace_request_metadata` DISABLE KEYS */;
/*!40000 ALTER TABLE `trace_request_metadata` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `trace_tags`
--

DROP TABLE IF EXISTS `trace_tags`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `trace_tags` (
  `key` varchar(250) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `value` varchar(8000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `request_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`key`,`request_id`),
  KEY `index_trace_tags_request_id` (`request_id`),
  CONSTRAINT `fk_trace_tags_request_id` FOREIGN KEY (`request_id`) REFERENCES `trace_info` (`request_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `trace_tags`
--

LOCK TABLES `trace_tags` WRITE;
/*!40000 ALTER TABLE `trace_tags` DISABLE KEYS */;
/*!40000 ALTER TABLE `trace_tags` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `webhook_events`
--

DROP TABLE IF EXISTS `webhook_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhook_events` (
  `webhook_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `entity` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `action` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  PRIMARY KEY (`webhook_id`,`entity`,`action`),
  KEY `idx_webhook_events_action` (`action`),
  KEY `idx_webhook_events_entity` (`entity`),
  KEY `idx_webhook_events_entity_action` (`entity`,`action`),
  CONSTRAINT `webhook_events_ibfk_1` FOREIGN KEY (`webhook_id`) REFERENCES `webhooks` (`webhook_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhook_events`
--

LOCK TABLES `webhook_events` WRITE;
/*!40000 ALTER TABLE `webhook_events` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhook_events` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `webhooks`
--

DROP TABLE IF EXISTS `webhooks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `webhooks` (
  `webhook_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `name` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `description` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `url` varchar(500) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL,
  `status` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'ACTIVE',
  `secret` varchar(1000) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin DEFAULT NULL,
  `creation_timestamp` bigint DEFAULT NULL,
  `last_updated_timestamp` bigint DEFAULT NULL,
  `deleted_timestamp` bigint DEFAULT NULL,
  `workspace` varchar(63) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_bin NOT NULL DEFAULT 'default',
  PRIMARY KEY (`webhook_id`),
  KEY `idx_webhooks_name` (`name`),
  KEY `idx_webhooks_status` (`status`),
  KEY `idx_webhooks_workspace` (`workspace`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `webhooks`
--

LOCK TABLES `webhooks` WRITE;
/*!40000 ALTER TABLE `webhooks` DISABLE KEYS */;
/*!40000 ALTER TABLE `webhooks` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `workspaces`
--

DROP TABLE IF EXISTS `workspaces`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `workspaces` (
  `name` varchar(63) COLLATE utf8mb4_0900_bin NOT NULL,
  `description` text COLLATE utf8mb4_0900_bin,
  `default_artifact_root` text COLLATE utf8mb4_0900_bin,
  `trace_archival_location` text COLLATE utf8mb4_0900_bin,
  `trace_archival_retention` varchar(32) COLLATE utf8mb4_0900_bin DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='MLflow 작업 공간';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `workspaces`
--

LOCK TABLES `workspaces` WRITE;
/*!40000 ALTER TABLE `workspaces` DISABLE KEYS */;
/*!40000 ALTER TABLE `workspaces` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'mlflow'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-07  2:22:37
