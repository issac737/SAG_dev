"""
MLflow 模拟实验脚本
模拟机器学习训练过程，记录常用指标到 MLflow
"""

import mlflow
import random
import time
from datetime import datetime

# MLflow 服务器地址
MLFLOW_TRACKING_URI = "http://192.168.110.10:5050"

def simulate_training_metrics(epoch: int, base_accuracy: float = 0.7):
    """模拟训练过程中的指标变化"""
    # 模拟随着训练轮次增加，指标逐渐提升
    progress = min(epoch / 50, 1.0)  # 50轮后趋于稳定
    noise = random.uniform(-0.02, 0.02)

    accuracy = base_accuracy + progress * 0.25 + noise
    precision = base_accuracy + progress * 0.22 + noise
    recall = base_accuracy + progress * 0.20 + noise
    f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

    # 损失函数逐渐下降
    loss = 1.0 - progress * 0.7 + abs(noise)

    return {
        "accuracy": min(accuracy, 0.99),
        "precision": min(precision, 0.98),
        "recall": min(recall, 0.97),
        "f1_score": min(f1_score, 0.98),
        "loss": max(loss, 0.1),
        "auc_roc": min(base_accuracy + progress * 0.28 + noise, 0.99),
    }


def run_mock_experiment(
    experiment_name: str = "mock_classification_experiment",
    run_name: str = None,
    epochs: int = 20,
    learning_rate: float = 0.001,
    batch_size: int = 32,
):
    """运行模拟实验"""

    # 设置 MLflow tracking URI
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    print(f"MLflow Tracking URI: {MLFLOW_TRACKING_URI}")

    # 创建或获取实验
    mlflow.set_experiment(experiment_name)
    print(f"Experiment: {experiment_name}")

    # 生成运行名称
    if run_name is None:
        run_name = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    with mlflow.start_run(run_name=run_name):
        print(f"Started run: {run_name}")

        # 记录超参数
        mlflow.log_params({
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "epochs": epochs,
            "optimizer": "Adam",
            "model_type": "RandomForest",
            "n_estimators": 100,
            "max_depth": 10,
        })
        print("Logged parameters")

        # 模拟训练过程
        base_accuracy = random.uniform(0.65, 0.75)

        for epoch in range(1, epochs + 1):
            metrics = simulate_training_metrics(epoch, base_accuracy)

            # 记录每个 epoch 的指标
            mlflow.log_metrics(metrics, step=epoch)

            print(f"Epoch {epoch:3d}/{epochs}: "
                  f"loss={metrics['loss']:.4f}, "
                  f"accuracy={metrics['accuracy']:.4f}, "
                  f"precision={metrics['precision']:.4f}, "
                  f"recall={metrics['recall']:.4f}, "
                  f"f1={metrics['f1_score']:.4f}")

            # 模拟训练时间
            time.sleep(0.5)

        # 记录最终指标
        final_metrics = simulate_training_metrics(epochs, base_accuracy)
        mlflow.log_metrics({
            "final_accuracy": final_metrics["accuracy"],
            "final_precision": final_metrics["precision"],
            "final_recall": final_metrics["recall"],
            "final_f1_score": final_metrics["f1_score"],
            "final_auc_roc": final_metrics["auc_roc"],
        })

        # 记录一些标签
        mlflow.set_tags({
            "model_version": "v1.0",
            "dataset": "mock_dataset",
            "task_type": "classification",
            "environment": "development",
        })

        print(f"\nExperiment completed!")
        print(f"Final metrics:")
        print(f"  - Accuracy:  {final_metrics['accuracy']:.4f}")
        print(f"  - Precision: {final_metrics['precision']:.4f}")
        print(f"  - Recall:    {final_metrics['recall']:.4f}")
        print(f"  - F1 Score:  {final_metrics['f1_score']:.4f}")
        print(f"  - AUC-ROC:   {final_metrics['auc_roc']:.4f}")

        return mlflow.active_run().info.run_id


def main():
    """主函数"""
    print("=" * 60)
    print("MLflow Mock Experiment Runner")
    print("=" * 60)

    # 运行多个实验来模拟不同的模型训练
    experiments = [
        {"experiment_name": "text_classification", "epochs": 15, "learning_rate": 0.001},
        {"experiment_name": "text_classification", "epochs": 15, "learning_rate": 0.01},
        {"experiment_name": "text_classification", "epochs": 15, "learning_rate": 0.0001},
    ]

    for i, exp_config in enumerate(experiments, 1):
        print(f"\n{'='*60}")
        print(f"Running experiment {i}/{len(experiments)}")
        print(f"{'='*60}\n")

        run_id = run_mock_experiment(**exp_config)
        print(f"\nRun ID: {run_id}")

        # 实验间隔
        if i < len(experiments):
            print("\nWaiting before next experiment...")
            time.sleep(2)

    print("\n" + "=" * 60)
    print("All experiments completed!")
    print(f"View results at: {MLFLOW_TRACKING_URI}")
    print("=" * 60)


if __name__ == "__main__":
    main()
