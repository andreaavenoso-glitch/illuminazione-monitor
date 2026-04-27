import { RecordDetail } from "@/components/RecordDetail";

export default function RecordDetailPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-6">
      <RecordDetail id={params.id} />
    </div>
  );
}
