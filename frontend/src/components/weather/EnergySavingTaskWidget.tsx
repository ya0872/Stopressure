import React from 'react';
import { useEnergySavingTasks } from '../../hooks/useEnergySavingTasks';

export const EnergySavingTaskWidget: React.FC = () => {
  const { tasks, isLoading } = useEnergySavingTasks();

  if (isLoading) return <div className="widget-box" style={{ opacity: 0.7 }}>提案を生成中...</div>;
  if (!tasks || tasks.length === 0) return null;

  return (
    <section>
      <div className="sec-title">本日の目標</div>
      <div>
        {tasks.map((task) => (
          <div key={task.id} className="suggest">
            <div className="suggest-text">{task.title}</div>
            {task.description && (
              <div className="suggest-reason">{task.description}</div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
};